# Generated by Django 3.0.5 on 2020-05-10 04:15

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('core', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('demographics', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='historicaldemographics',
            name='history_user',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='historicaldemographics',
            name='patient',
            field=models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='core.Patient'),
        ),
        migrations.AddField(
            model_name='historicaldemographics',
            name='transportation',
            field=models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='demographics.TransportationOption'),
        ),
        migrations.AddField(
            model_name='historicaldemographics',
            name='work_status',
            field=models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='demographics.WorkStatus'),
        ),
        migrations.AddField(
            model_name='demographics',
            name='annual_income',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='demographics.IncomeRange'),
        ),
        migrations.AddField(
            model_name='demographics',
            name='chronic_condition',
            field=models.ManyToManyField(blank=True, to='demographics.ChronicCondition'),
        ),
        migrations.AddField(
            model_name='demographics',
            name='education_level',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='demographics.EducationLevel'),
        ),
        migrations.AddField(
            model_name='demographics',
            name='patient',
            field=models.OneToOneField(null=True, on_delete=django.db.models.deletion.CASCADE, to='core.Patient'),
        ),
        migrations.AddField(
            model_name='demographics',
            name='resource_access',
            field=models.ManyToManyField(blank=True, to='demographics.ResourceAccess', verbose_name='Access to Resources'),
        ),
        migrations.AddField(
            model_name='demographics',
            name='transportation',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='demographics.TransportationOption'),
        ),
        migrations.AddField(
            model_name='demographics',
            name='work_status',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='demographics.WorkStatus'),
        ),
    ]
