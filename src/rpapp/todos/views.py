from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from rpapp.todos.forms import ScimUserForm, TodoForm
from rpapp.todos.models import Todo
from rpapp.todos.scim import ScimError, create_user, list_users


def todo_list(request: HttpRequest) -> HttpResponse:
    todos = Todo.objects.filter(owner=request.user)
    return render(request, "todos/todo_list.html", {"todos": todos})


def todo_create(request: HttpRequest) -> HttpResponse:
    form = TodoForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        todo = form.save(commit=False)
        todo.owner = request.user
        todo.save()
        messages.success(request, "Todoを作成しました。")
        return redirect("todo-list")
    return render(request, "todos/todo_form.html", {"form": form, "heading": "Todoを追加"})


def todo_update(request: HttpRequest, pk: int) -> HttpResponse:
    todo = get_object_or_404(Todo, pk=pk, owner=request.user)
    form = TodoForm(request.POST or None, instance=todo)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Todoを更新しました。")
        return redirect("todo-list")
    return render(
        request, "todos/todo_form.html", {"form": form, "heading": "Todoを編集"}
    )


@require_POST
def todo_delete(request: HttpRequest, pk: int) -> HttpResponse:
    todo = get_object_or_404(Todo, pk=pk, owner=request.user)
    todo.delete()
    messages.success(request, "Todoを削除しました。")
    return redirect("todo-list")


def is_admin(user) -> bool:
    return user.is_authenticated and user.is_staff


@user_passes_test(is_admin)
def user_list(request: HttpRequest) -> HttpResponse:
    try:
        users = list_users()
    except ScimError as exc:
        messages.error(request, str(exc))
        users = []
    return render(request, "todos/user_list.html", {"users": users})


@user_passes_test(is_admin)
def user_create(request: HttpRequest) -> HttpResponse:
    form = ScimUserForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            create_user(
                user_name=form.cleaned_data["user_name"],
                email=form.cleaned_data["email"],
                given_name=form.cleaned_data["given_name"],
                family_name=form.cleaned_data["family_name"],
            )
        except ScimError as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, "SCIM経由でユーザーを登録しました。")
            return redirect("user-list")
    return render(request, "todos/user_form.html", {"form": form})
