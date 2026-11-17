import ssl

from django.core.servers.basehttp import ThreadedWSGIServer
from sslserver.management.commands import runsslserver as sslserver_command


class SecureHTTPServer(ThreadedWSGIServer):
    def __init__(self, address, handler_cls, certificate, key, ipv6=False):
        super().__init__(address, handler_cls, ipv6=ipv6)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certfile=certificate, keyfile=key)
        self.socket = context.wrap_socket(self.socket, server_side=True)


class Command(sslserver_command.Command):
    def inner_run(self, *args, **options):
        # django-sslserver 0.22 uses ssl.wrap_socket, removed in Python 3.12.
        original_server = sslserver_command.SecureHTTPServer
        sslserver_command.SecureHTTPServer = SecureHTTPServer
        try:
            return super().inner_run(*args, **options)
        finally:
            sslserver_command.SecureHTTPServer = original_server
