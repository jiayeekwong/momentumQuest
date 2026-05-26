from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('resources', '0002_copy_learning_resources_from_jobs'),
    ]

    operations = [
        migrations.CreateModel(
            name='ResourceScrapeLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('started_at', models.DateTimeField(auto_now_add=True)),
                ('finished_at', models.DateTimeField(blank=True, null=True)),
                ('status', models.CharField(
                    choices=[('SUCCESS', 'Success'), ('PARTIAL', 'Partial (some platforms failed)'), ('FAILED', 'Failed')],
                    default='FAILED',
                    max_length=20,
                )),
                ('platforms_scraped', models.JSONField(default=list)),
                ('resources_scraped', models.IntegerField(default=0)),
                ('resources_created', models.IntegerField(default=0)),
                ('resources_updated', models.IntegerField(default=0)),
                ('resources_deactivated', models.IntegerField(default=0)),
                ('error_message', models.TextField(blank=True)),
            ],
            options={
                'ordering': ['-started_at'],
            },
        ),
    ]
