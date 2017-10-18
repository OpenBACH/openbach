from django.contrib.auth.models import User
from django.db.models.signals import pre_delete
from django.dispatch import receiver


@receiver(pre_delete, sender=User)
def assign_private_project_to_superuser(sender, instance, **kwargs):
    super_user = User.objects.filter(is_superuser=True).first()
    if super_user is None or super_user == instance:
        return

    for project in instance.private_projects.all():
        if project.owners.count() == 1:
            project.owners.add(super_user)
