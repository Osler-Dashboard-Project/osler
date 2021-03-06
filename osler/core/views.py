from builtins import zip
import collections
import datetime

from django.conf import settings
from django.apps import apps
from django.shortcuts import get_object_or_404, render
from django.http import HttpResponseRedirect, HttpResponseServerError
from django.views.generic.edit import FormView, UpdateView
from django.views.generic.list import ListView
from django.urls import reverse
from django.core.exceptions import ImproperlyConfigured
from django.db.models import Prefetch
from django.utils.http import url_has_allowed_host_and_scheme

from osler.workup import models as workupmodels
from osler.referral.models import Referral, FollowupRequest, PatientContact
from osler.vaccine.models import VaccineFollowup
from osler.appointment.models import Appointment

from osler.core import models as core_models
from osler.core import forms
from osler.core import utils


def get_current_provider_type(request):
    '''
    Given the request, produce the ProviderType of the logged in user. This is
    done using session data.
    '''
    return get_object_or_404(core_models.ProviderType,
                             pk=request.session['clintype_pk'])


class NoteFormView(FormView):
    note_type = None

    def get_context_data(self, **kwargs):
        '''Inject self.note_type and patient into the context.'''

        if self.note_type is None:
            raise ImproperlyConfigured("NoteCreate view must have"
                                       "'note_type' variable set.")

        context = super(NoteFormView, self).get_context_data(**kwargs)
        context['note_type'] = self.note_type

        if 'pt_id' in self.kwargs:
            context['patient'] = core_models.Patient.objects. \
                get(pk=self.kwargs['pt_id'])

        return context


class NoteUpdate(UpdateView):
    note_type = None

    def get_context_data(self, **kwargs):
        '''Inject self.note_type as the note type.'''

        if self.note_type is None:
            raise ImproperlyConfigured("NoteUpdate view must have"
                                       "'note_type' variable set.")

        context = super(NoteUpdate, self).get_context_data(**kwargs)
        context['note_type'] = self.note_type

        return context

    # TODO: add shared form_valid code here from all subclasses.


class ProviderCreate(FormView):
    '''A view for creating a new Provider to match an existing User.'''
    template_name = 'core/new-provider.html'
    form_class = forms.ProviderForm

    def form_valid(self, form):
        provider = form.save(commit=False)
        # check that user did not previously create a provider
        if not hasattr(self.request.user, 'provider'):
            provider.associated_user = self.request.user
            # populate the User object with the name data from
            # the Provider form
            user = provider.associated_user
            user.name = provider.name()
            user.save()
            provider.save()
            form.save_m2m()

        if 'next' in self.request.GET:
            next_url = self.request.GET['next']
        else:
            next_url = reverse('home')

        return HttpResponseRedirect(next_url)

    def get_context_data(self, **kwargs):
        context = super(ProviderCreate, self).get_context_data(**kwargs)
        context['next'] = self.request.GET.get('next')
        return context


class ProviderUpdate(UpdateView):
    """For updating a provider, e.g. used during a new school year when
    preclinicals become clinicals. Set needs_update to false using
    require_providers_update() in core.models
    """
    template_name = 'core/provider-update.html'
    model = core_models.Provider
    form_class = forms.ProviderForm

    def get_object(self):
        """Returns the request's provider
        """
        return self.request.user.provider

    def form_valid(self, form):
        provider = form.save(commit=False)
        provider.needs_updating = False
        # populate the User object with the name data from
        # the Provider form
        user = provider.associated_user
        user.name = provider.name()
        user.save()
        provider.save()
        form.save_m2m()

        return HttpResponseRedirect(
            self.request.GET.get('next', reverse('home')))


class ActionItemCreate(NoteFormView):
    """A view for creating ActionItems using the ActionItemForm."""
    template_name = 'core/form_submission.html'
    form_class = forms.ActionItemForm
    note_type = 'Action Item'

    def form_valid(self, form):
        '''Set the patient, provider, and written timestamp for the item.'''
        pt = get_object_or_404(core_models.Patient, pk=self.kwargs['pt_id'])
        ai = form.save(commit=False)

        ai.completion_date = None
        ai.author = self.request.user.provider
        ai.author_type = get_current_provider_type(self.request)
        ai.patient = pt

        ai.save()

        return HttpResponseRedirect(reverse("core:patient-detail",
                                            args=(pt.id,)))


class ActionItemUpdate(NoteUpdate):
    template_name = "core/form-update.html"
    model = core_models.ActionItem
    form_class = forms.ActionItemForm
    note_type = "Action Item"

    def get_success_url(self):
        pt = self.object.patient
        return reverse("core:patient-detail", args=(pt.id, ))


class PatientUpdate(UpdateView):
    template_name = 'core/patient-update.html'
    model = core_models.Patient
    form_class = forms.PatientForm

    def form_valid(self, form):
        pt = form.save()
        pt.save()

        return HttpResponseRedirect(reverse("core:patient-detail",
                                            args=(pt.id,)))


class PreIntakeSelect(ListView):
    """Allows users to see all patients with similar name to a
    particular patient first and last name. Allows user to open one of
    the simmilarly named patients, or create a new patient
    """
    template_name = 'core/preintake-select.html'
    new_pt_url = ""

    def parse_url_querystring(self):

        return utils.get_names_from_url_query_dict(self.request)

    def get_queryset(self):
        initial = self.parse_url_querystring()
        if (initial.get('first_name', None) is None or
            initial.get('last_name', None) is None):
            return []
        possible_duplicates = utils.return_duplicates(initial.get(
            'first_name', None), initial.get('last_name', None))
        return possible_duplicates

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super(PreIntakeSelect, self).get_context_data(**kwargs)
        initial = self.parse_url_querystring()
        context['first_name'] = initial.get('first_name', None)
        context['last_name'] = initial.get('last_name', None)
        context['new_pt_url'] = "%s?%s=%s&%s=%s" % (
            reverse("core:intake"),
            "first_name", initial.get('first_name', None),
            "last_name", initial.get('last_name', None))
        context['home'] = reverse("home")
        return context


class PreIntake(FormView):
    """A view for ensuring new patient is not already in the database.

    Searches if there is a patient with same, or similar first and last
    name. If none similar directs to patient intake;  If one or more similar
    directs to preintake-select urls are sent with first and last name in
    query string notation
    """

    template_name = 'core/preintake.html'
    form_class = forms.DuplicatePatientForm

    def form_valid(self, form):
        first_name_str = form.cleaned_data['first_name'].capitalize()
        last_name_str = form.cleaned_data['last_name'].capitalize()
        matching_patients = utils.return_duplicates(first_name_str,
                                                    last_name_str)

        querystr = '%s=%s&%s=%s' % ("first_name", first_name_str,
                                    "last_name", last_name_str)
        if len(matching_patients) > 0:
            intake_url = "%s?%s" % (reverse("core:preintake-select"), querystr)
            return HttpResponseRedirect(intake_url)

        intake_url = "%s?%s" % (reverse("core:intake"), querystr)
        return HttpResponseRedirect(intake_url)


class PatientCreate(FormView):
    """A view for creating a new patient using PatientForm."""
    template_name = 'core/intake.html'
    form_class = forms.PatientForm

    def form_valid(self, form):
        pt = form.save()
        pt.save()
        return HttpResponseRedirect(reverse("demographics-create",
                                            args=(pt.id,)))

    def get_initial(self):
        initial = super(PatientCreate, self).get_initial()

        initial.update(utils.get_names_from_url_query_dict(self.request))
        return initial


class DocumentUpdate(NoteUpdate):
    template_name = "core/form-update.html"
    model = core_models.Document
    form_class = forms.DocumentForm
    note_type = "Document"

    def get_success_url(self):
        doc = self.object
        return reverse("core:document-detail", args=(doc.id, ))


class DocumentCreate(NoteFormView):
    '''A view for uploading a document'''
    template_name = 'core/form_submission.html'
    form_class = forms.DocumentForm
    note_type = 'Document'

    def form_valid(self, form):
        doc = form.save(commit=False)

        pt = get_object_or_404(core_models.Patient, pk=self.kwargs['pt_id'])
        doc.patient = pt
        doc.author = self.request.user.provider
        doc.author_type = get_current_provider_type(self.request)

        doc.save()

        return HttpResponseRedirect(reverse("core:patient-detail", args=(pt.id,)))


def choose_clintype(request):
    RADIO_CHOICE_KEY = 'radio-roles'

    redirect_to = request.GET['next']
    if not url_has_allowed_host_and_scheme(url=redirect_to,
                                           allowed_hosts=request.get_host()):
        redirect_to = reverse('home')

    if request.POST:
        request.session['clintype_pk'] = request.POST[RADIO_CHOICE_KEY]
        active_provider_type = get_current_provider_type(request)
        request.session['signs_charts'] = active_provider_type.signs_charts
        request.session['staff_view'] = active_provider_type.staff_view

        return HttpResponseRedirect(redirect_to)

    if request.GET:
        role_options = request.user.provider.clinical_roles.all()

        if len(role_options) == 1:
            request.session['clintype_pk'] = role_options[0].pk
            active_provider_type = get_current_provider_type(request)
            request.session['signs_charts'] = active_provider_type.signs_charts
            request.session['staff_view'] = active_provider_type.staff_view
            return HttpResponseRedirect(redirect_to)
        elif len(role_options) == 0:
            return HttpResponseServerError(
                "Fatal: your Provider register is corrupted, and lacks "
                "ProviderTypes. Report this error!")
        else:
            return render(request, 'core/role-choice.html',
                          {'roles': role_options,
                           'choice_key': RADIO_CHOICE_KEY})


def home_page(request):
    return HttpResponseRedirect(reverse(settings.OSLER_DEFAULT_DASHBOARD))

#     active_provider_type = get_object_or_404(core_models.ProviderType,
#                                              pk=request.session['clintype_pk'])

#     if active_provider_type.signs_charts:
#         title = "Attending Tasks"
#         lists = [
#             {'url': 'filter=unsigned_workup', 'title': "Unsigned Workups",
#              'identifier': 'unsignedwu', 'active': True},
#             {'url': 'filter=active', 'title': "Active Patients",
#              'identifier': 'activept', 'active': False}]

#     elif active_provider_type.staff_view:
#         title = "Coordinator Tasks"
#         lists = [
#             {'url': 'filter=active', 'title': "Active Patients",
#              'identifier': 'activept', 'active': True},
#             {'url': 'filter=ai_priority', 'title': "Priority Action Items",
#              'identifier': 'priorityai', 'active': False},
#             {'url': 'filter=ai_active', 'title': "Active Action Items",
#              'identifier': 'activeai', 'active': False},
#             {'url': 'filter=ai_inactive', 'title': "Pending Action Items",
#              'identifier': 'pendingai', 'active': False},
#             {'url': 'filter=unsigned_workup', 'title': "Unsigned Workups",
#              'identifier': 'unsignedwu', 'active': False},
#             {'url': 'filter=user_cases', 'title': "My Cases",
#              'identifier': 'usercases', 'active': False}
#         ]

#     else:
#         title = "Active Patients"
#         lists = [
#             {'url': 'filter=active',
#              'title': "Active Patients",
#              'identifier': 'activept',
#              'active': True}]

#     # remove last '/' before adding because there no '/' between
#     # /api/pt_list and .json, but reverse generates '/api/pt_list/'
#     api_url = reverse('pt_list_api')[:-1] + '.json/?'

#     return render(request, 'core/patient_list.html',
#                   {'lists': json.dumps(lists),
#                    'title': title,
#                    'api_url': api_url})


def patient_detail(request, pk):

    pt = get_object_or_404(core_models.Patient, pk=pk)

    #   Special zipped list of action item types so they can be looped over.
    #   List 1: Labels for the panel objects of the action items
    #   List 2: Action Item lists based on type (active, pending, completed)
    #   List 3: Title labels for the action items
    #   List 4: True and False determines if the link should be for
    #           done_action_item or update_action_item

    active_ais = []
    inactive_ais = []
    done_ais = []

    # Add action items for apps that are turned on in Osler's base settings
    # OSLER_TODO_LIST_MANAGERS contains app names like referral which contain
    # tasks for clinical teams to carry out (e.g., followup with patient)
    for app, model in settings.OSLER_TODO_LIST_MANAGERS:
        ai = apps.get_model(app, model)

        active_ais.extend(ai.objects.get_active(patient=pt))
        inactive_ais.extend(ai.objects.get_inactive(patient=pt))
        done_ais.extend(ai.objects.get_completed(patient=pt))

    # Calculate the total number of action items for this patient,
    # This total includes all apps that that have associated
    # tasks requiring clinical followup (e.g., referral followup request)
    total_ais = len(active_ais) + len(inactive_ais) + len(done_ais)

    zipped_ai_list = list(zip(
        ['collapse6', 'collapse7', 'collapse8'],
        [active_ais, inactive_ais, done_ais],
        ['Active Action Items', 'Pending Action Items',
         'Completed Action Items'],
        [True, True, False]))

    # Provide referral list for patient page (includes specialty referrals)
    referrals = Referral.objects.filter(
        patient=pt,
        followuprequest__in=FollowupRequest.objects.all()
    )

    # Add FQHC referral status
    # Note it is possible for a patient to have been referred multiple times
    # This creates some strage cases (e.g., first referral was lost to followup
    # but the second one was successful). In these cases, the last referral
    # status becomes the current status
    fqhc_referrals = Referral.objects.filter(patient=pt, kind__is_fqhc=True)
    referral_status_output = Referral.aggregate_referral_status(fqhc_referrals)

    # Pass referral follow up set to page
    referral_followups = PatientContact.objects.filter(patient=pt)
    #Pass vaccine follow up set to page
    vaccine_followups = VaccineFollowup.objects.filter(patient=pt)
    total_followups = referral_followups.count() + len(pt.followup_set()) + vaccine_followups.count()

    appointments = Appointment.objects \
        .filter(patient=pt) \
        .order_by('clindate', 'clintime')
    # d = collections.OrderedDict()
    # for a in appointments:
    #     if a.clindate in d:
    #         d[a.clindate].append(a)
    #     else:
    #         d[a.clindate] = [a]

    future_date_appointments = appointments.filter(
        clindate__gte=datetime.date.today()).order_by('clindate', 'clintime')
    previous_date_appointments = appointments.filter(
        clindate__lt=datetime.date.today()).order_by('-clindate', 'clintime')

    future_apt = collections.OrderedDict()
    for a in future_date_appointments:
        if a.clindate in future_apt:
            future_apt[a.clindate].append(a)
        else:
            future_apt[a.clindate] = [a]

    previous_apt = collections.OrderedDict()
    for a in previous_date_appointments:
        if a.clindate in previous_apt:
            previous_apt[a.clindate].append(a)
        else:
            previous_apt[a.clindate] = [a]

    zipped_apt_list = list(zip(
        ['collapse9', 'collapse10'],
        [future_date_appointments, previous_date_appointments],
        ['Future Appointments', 'Past Appointments'],
        [future_apt, previous_apt]))

    return render(request,
                  'core/patient_detail.html',
                  {'zipped_ai_list': zipped_ai_list,
                   'total_ais': total_ais,
                   'referral_status': referral_status_output,
                   'referrals': referrals,
                   'referral_followups': referral_followups,
                   'vaccine_followups': vaccine_followups,
                   'total_followups': total_followups,
                   'patient': pt,
                   'appointments_by_date': future_apt,
                   'zipped_apt_list': zipped_apt_list})


def all_patients(request):
    """
    Query is written to minimize hits to the database; number of db hits can be
        see on the django debug toolbar.
    """
    patient_list = core_models.Patient.objects.all() \
        .order_by('last_name') \
        .select_related('gender') \
        .prefetch_related('case_managers') \
        .prefetch_related(Prefetch(
            'workup_set',
            queryset=workupmodels.Workup.objects.order_by(
                'clinic_day__clinic_date'))) \
        .prefetch_related('actionitem_set')

    # Don't know how to prefetch history
    # https://stackoverflow.com/questions/45713517/use-prefetch-related-in-django-simple-history
    # Source code is https://github.com/treyhunner/django-simple-history/blob/master/simple_history/models.py if we want to try to figure out

    return render(request,
                  'core/all_patients.html',
                  {'object_list': patient_list})


def patient_activate_detail(request, pk):
    pt = get_object_or_404(core_models.Patient, pk=pk)

    pt.toggle_active_status()

    pt.save()

    return HttpResponseRedirect(reverse("core:patient-detail", args=(pt.id,)))


def patient_activate_home(request, pk):
    pt = get_object_or_404(core_models.Patient, pk=pk)

    pt.toggle_active_status()

    pt.save()

    return HttpResponseRedirect(reverse("home"))


def done_action_item(request, ai_id):
    ai = get_object_or_404(core_models.ActionItem, pk=ai_id)
    ai.mark_done(request.user.provider)
    ai.save()

    return HttpResponseRedirect(reverse("new-actionitem-followup",
                                        kwargs={'pt_id':ai.patient.pk,
                                        'ai_id':ai.pk}))


def reset_action_item(request, ai_id):
    ai = get_object_or_404(core_models.ActionItem, pk=ai_id)
    ai.clear_done()
    ai.save()
    return HttpResponseRedirect(reverse("core:patient-detail",
                                        args=(ai.patient.id,)))
