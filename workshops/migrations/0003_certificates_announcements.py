import django.core.validators
import django.db.models.deletion
from django.db import migrations, models

import workshops.models


class Migration(migrations.Migration):

    dependencies = [
        ("workshops", "0002_gallery_feedback_payment"),
    ]

    operations = [
        migrations.AddField(
            model_name="workshop",
            name="cert_template",
            field=models.ImageField(
                blank=True,
                help_text="This workshop's blank certificate as a JPG or PNG. The student's name is written on it automatically.",
                storage=workshops.models.private_cert_storage,
                upload_to="",
                verbose_name="Certificate template",
            ),
        ),
        migrations.AddField(
            model_name="workshop",
            name="cert_name_x",
            field=models.FloatField(
                default=50.0,
                validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(100)],
                verbose_name="Name position, left to right (%)",
            ),
        ),
        migrations.AddField(
            model_name="workshop",
            name="cert_name_y",
            field=models.FloatField(
                default=50.0,
                validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(100)],
                verbose_name="Name position, top to bottom (%)",
            ),
        ),
        migrations.AddField(
            model_name="workshop",
            name="cert_font_size",
            field=models.FloatField(
                default=5.0,
                validators=[django.core.validators.MinValueValidator(0.5), django.core.validators.MaxValueValidator(20)],
                verbose_name="Name size (% of certificate width)",
            ),
        ),
        migrations.AddField(
            model_name="workshop",
            name="cert_color",
            field=models.CharField(default="#1f2937", max_length=7, verbose_name="Name colour"),
        ),
        migrations.AddField(
            model_name="workshop",
            name="cert_font",
            field=models.CharField(blank=True, max_length=80, verbose_name="Name font file"),
        ),
        migrations.AddField(
            model_name="workshop",
            name="announced_at",
            field=models.DateTimeField(blank=True, editable=False, null=True, verbose_name="First announced to past attendees"),
        ),
        migrations.CreateModel(
            name="Unsubscribed",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("email", models.EmailField(max_length=254, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"verbose_name_plural": "Unsubscribed emails"},
        ),
        migrations.CreateModel(
            name="Announcement",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("email", models.EmailField(max_length=254)),
                ("name", models.CharField(blank=True, max_length=100)),
                ("status", models.CharField(max_length=200)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "workshop",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="announcements",
                        to="workshops.workshop",
                    ),
                ),
            ],
        ),
        migrations.AddConstraint(
            model_name="announcement",
            constraint=models.UniqueConstraint(fields=("workshop", "email"), name="one_announcement_per_person"),
        ),
    ]
