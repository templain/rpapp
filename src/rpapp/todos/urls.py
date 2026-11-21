from django.urls import path

from rpapp.todos import views

urlpatterns = [
    path("", views.todo_list, name="todo-list"),
    path("todos/new/", views.todo_create, name="todo-create"),
    path("todos/<int:pk>/edit/", views.todo_update, name="todo-update"),
    path("todos/<int:pk>/delete/", views.todo_delete, name="todo-delete"),
    path("manage/users/", views.user_list, name="user-list"),
    path("manage/users/new/", views.user_create, name="user-create"),
    path("manage/users/<str:user_id>/delete/", views.user_delete, name="user-delete"),
]
