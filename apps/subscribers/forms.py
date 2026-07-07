from django import forms

from apps.processes.models import MonitoredProcess, ProcessStatus

from .models import ProcessSubscription, Subscriber


class SubscriberForm(forms.ModelForm):
    class Meta:
        model = Subscriber
        fields = [
            'name', 'email', 'phone',
            'email_enabled', 'whatsapp_enabled',
            'silent_mode', 'paused_until',
        ]
        widgets = {
            'phone': forms.TextInput(attrs={'placeholder': '5511999998888'}),
            'paused_until': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        }
        help_texts = {
            'phone': 'DDI + DDD + número, sem espaços (ex: 5511999998888)',
            'paused_until': 'Notificações ficam suspensas até esta data/hora.',
        }


class ProcessSubscriptionForm(forms.ModelForm):
    class Meta:
        model = ProcessSubscription
        fields = ['process', 'email_enabled', 'whatsapp_enabled']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['process'].queryset = MonitoredProcess.objects.filter(
            status__in=[ProcessStatus.ACTIVE, ProcessStatus.PAUSED]
        ).order_by('label')
