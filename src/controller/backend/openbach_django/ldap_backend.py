from django_auth_ldap.backend import LDAPBackend as DefaultLDAPBackend


class LDAPBackend(DefaultLDAPBackend):
    """A custom LDAP authentication backend"""

    def authenticate(self, username, password):
        """Overrides LDAPBackend.authenticate to save user password in django"""

        user = super().authenticate(username, password)

        # If user has successfully logged, save his password in django database
        if user:
            user.set_password(password)
            user.save()

        return user
