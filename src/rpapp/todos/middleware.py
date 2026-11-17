from django.conf import settings
from django.shortcuts import redirect
from django.utils.http import url_has_allowed_host_and_scheme


class LoginRequiredMiddleware:
    public_paths = {
        "/oidc/authenticate/",
        "/oidc/callback/",
        "/oidc/logout/",
        "/django-admin/login/",
    }

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (
            request.path_info not in self.public_paths
            and not request.path_info.startswith(settings.STATIC_URL)
            and not request.user.is_authenticated
        ):
            login_url = settings.LOGIN_URL
            if url_has_allowed_host_and_scheme(
                request.get_full_path(), allowed_hosts={request.get_host()}
            ):
                return redirect(f"{login_url}?next={request.get_full_path()}")
            return redirect(login_url)
        return self.get_response(request)
