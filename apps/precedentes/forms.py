from django import forms

from .models import PrecedentCase, PrecedentEntity, PrecedentFact


class PrecedentCaseForm(forms.ModelForm):
    class Meta:
        model = PrecedentCase
        fields = ['titulo', 'cliente', 'notas']
        widgets = {'notas': forms.Textarea(attrs={'rows': 3})}


class PrecedentEntityForm(forms.ModelForm):
    class Meta:
        model = PrecedentEntity
        fields = ['papel', 'razao_social', 'cnpj', 'pais']


class PrecedentFactForm(forms.ModelForm):
    class Meta:
        model = PrecedentFact
        fields = ['campo', 'valor', 'status', 'fonte_descricao', 'fonte_url', 'citacao']
        widgets = {'citacao': forms.Textarea(attrs={'rows': 2})}


class PrecedentFactCorrectionForm(forms.ModelForm):
    motivo = forms.CharField(widget=forms.Textarea(attrs={'rows': 2}), required=True, label='Motivo da correção')

    class Meta:
        model = PrecedentFact
        fields = ['campo', 'valor', 'status', 'fonte_descricao', 'fonte_url', 'citacao']
        widgets = {'citacao': forms.Textarea(attrs={'rows': 2})}


class PrecedentAnalysisForm(forms.Form):
    texto = forms.CharField(widget=forms.Textarea(attrs={'rows': 3}), label='Análise')
    fact_ids = forms.ModelMultipleChoiceField(
        queryset=PrecedentFact.objects.none(), required=True, label='Fatos-base',
    )

    def __init__(self, *args, case=None, **kwargs):
        super().__init__(*args, **kwargs)
        if case is not None:
            self.fields['fact_ids'].queryset = PrecedentFact.objects.filter(
                entity__case=case, is_current=True,
            )
