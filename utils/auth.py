from userprofile.models import Users
from rest_framework.exceptions import AuthenticationFailed, NotAuthenticated

class Authtication(object):
    def authenticate(self, request):
        token = request.META.get('HTTP_TOKEN')
        if not token:
            raise NotAuthenticated("Please add a token to your request headers")

        user = Users.objects.filter(openid__exact=str(token)).first()
        if user is None:
            raise AuthenticationFailed("User does not exist")
        # The legacy API uses request.auth.openid throughout the view layer.
        return (True, user)

    def authenticate_header(self, request):
        return 'Token'
