from django import forms

from rpapp.todos.models import Todo


class TodoForm(forms.ModelForm):
    class Meta:
        model = Todo
        fields = ["title", "description", "is_completed"]
        widgets = {
            "title": forms.TextInput(attrs={"autocomplete": "off"}),
            "description": forms.Textarea(attrs={"rows": 4}),
        }


class ScimUserForm(forms.Form):
    user_name = forms.CharField(max_length=255, label="ユーザー名")
    email = forms.EmailField(label="メールアドレス")
    given_name = forms.CharField(max_length=100, label="名")
    family_name = forms.CharField(max_length=100, label="姓")
