from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    path("django-admin/", admin.site.urls),
    path("oidc/", include("mozilla_django_oidc.urls")),
    path("", include("rpapp.todos.urls")),
    path("", RedirectView.as_view(pattern_name="todo-list", permanent=False)),
]
