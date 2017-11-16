from django.contrib.auth.models import User
from django.db.models.signals import pre_delete
from django.dispatch import receiver


@receiver(pre_delete, sender=User)
def assign_private_project_to_superuser(sender, instance, **kwargs):
    super_users = User.objects.filter(is_superuser=True).exclude(id=instance.id)
    if not super_users:
        return

    for project in instance.private_projects.all():
        if project.owners.count() == 1:
            project.owners.add(*super_users)
