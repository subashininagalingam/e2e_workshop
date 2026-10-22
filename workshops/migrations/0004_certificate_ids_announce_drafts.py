import django.core.validators
import django.db.models.deletion
from django.db import migrations, models

import workshops.models


def _pct(name, default, hi=100, lo=0):
    return models.FloatField(
        default=default,
        validators=[django.core.validators.MinValueValidator(lo), django.core.validators.MaxValueValidator(hi)],
        verbose_name=name,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("workshops", "0003_certificates_announcements"),
    ]

    operations = [
        migrations.AddField(model_name="workshop", name="cert_id_prefix",
                            field=models.CharField(blank=True, max_length=60, verbose_name="Certificate ID prefix")),
        migrations.AddField(model_name="workshop", name="cert_id_next",
                            field=models.PositiveIntegerField(default=1, verbose_name="Next certificate number")),
        migrations.AddField(model_name="workshop", name="cert_id_width",
                            field=models.PositiveSmallIntegerField(default=0, verbose_name="Certificate number digits")),
        migrations.AddField(model_name="workshop", name="cert_id_x", field=_pct("ID position, left to right (%)", 50.0)),
        migrations.AddField(model_name="workshop", name="cert_id_y", field=_pct("ID position, top to bottom (%)", 88.0)),
        migrations.AddField(model_name="workshop", name="cert_id_size", field=_pct("ID size (% of certificate width)", 1.6, hi=10, lo=0.5)),
        migrations.AddField(
            model_name="workshop", name="fee_for_certificate",
            field=models.BooleanField(
                default=True,
                help_text="Ticked: the workshop is free to join, and students choose Yes/No for a paid certificate. "
                          "Unticked: everyone must pay the fee to register.",
                verbose_name="Fee is for the certificate (optional)"),
        ),
        migrations.CreateModel(
            name="AnnouncementDraft",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("subject", models.CharField(blank=True, max_length=200)),
                ("message", models.TextField(blank=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("workshop", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE,
                                                  related_name="announce_draft", to="workshops.workshop")),
            ],
        ),
        migrations.CreateModel(
            name="AnnouncementFile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("file", models.FileField(storage=workshops.models.private_announce_storage, upload_to="")),
                ("original_name", models.CharField(max_length=150)),
                ("size", models.PositiveIntegerField(default=0)),
                ("draft", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                            related_name="files", to="workshops.announcementdraft")),
            ],
        ),
    ]
