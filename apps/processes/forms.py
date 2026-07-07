from django import forms

from .models import MonitoredProcess


class ProcessForm(forms.ModelForm):
    class Meta:
        model = MonitoredProcess
        fields = ['label', 'source', 'check_interval_seconds', 'status', 'notes']
        widgets = {
            'label': forms.TextInput(attrs={
                'placeholder': 'Ex: Fusão XYZ — Ato de Concentração',
                'class': 'form-input',
            }),
            'source': forms.TextInput(attrs={
                'placeholder': 'URL pública ou número (ex: 08700.005905/2026-38)',
                'class': 'form-input',
            }),
            'notes': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': 'Observações internas sobre este processo...',
                'class': 'form-input',
            }),
        }
        help_texts = {
            'source': 'Informe a URL pública do processo no SEI/CADE ou o número de protocolo.',
            'check_interval_seconds': 'Mínimo: 1500 s (25 min). Seja responsável com a página pública.',
        }

    def clean_check_interval_seconds(self):
        value = self.cleaned_data.get('check_interval_seconds')
        if value and value < 1500:
            raise forms.ValidationError('O intervalo mínimo é 1500 segundos (25 minutos).')
        return value

    def clean_source(self):
        source = self.cleaned_data.get('source', '').strip()
        if not source:
            raise forms.ValidationError('Informe uma URL pública ou número de processo.')
        from urllib.parse import urlparse
        parsed = urlparse(source)
        if parsed.scheme or parsed.netloc:
            if parsed.scheme not in ('http', 'https') or not parsed.netloc:
                raise forms.ValidationError('A URL precisa começar com http:// ou https://.')
            _block_ssrf(parsed)
        elif len(source) < 4:
            raise forms.ValidationError('Informe um número de processo/protocolo válido.')
        return source


def _block_ssrf(parsed) -> None:
    """
    Impede que URLs apontem para endereços de rede interna (SSRF).
    Resolve o hostname via DNS e rejeita IPs privados/loopback/link-local.
    """
    import ipaddress
    import socket

    hostname = parsed.hostname
    if not hostname:
        return

    # Rejeita diretamente se o hostname já parecer privado sem precisar resolver
    _BLOCKED_KEYWORDS = ('localhost', '0.0.0.0', '::1')
    if any(hostname == kw for kw in _BLOCKED_KEYWORDS):
        raise forms.ValidationError(
            'URL aponta para rede interna. Informe uma URL pública acessível.'
        )

    # Resolve para IP e verifica se é privado/reservado
    try:
        addr = socket.getaddrinfo(hostname, None)[0][4][0]
        ip = ipaddress.ip_address(addr)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise forms.ValidationError(
                'URL aponta para rede interna. Informe uma URL pública acessível.'
            )
    except forms.ValidationError:
        raise
    except OSError:
        # Hostname não resolvível — deixa passar; o cliente HTTP falhará em tempo de checagem
        pass
