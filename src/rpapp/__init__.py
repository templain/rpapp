def main() -> None:
    """Run the Django development server."""
    from django.core.management import execute_from_command_line

    execute_from_command_line(["manage.py", "runserver"])
