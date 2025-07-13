from django import forms
from .models import Board


class MarkEntryForm(forms.Form):
    def __init__(self, *args, **kwargs):
        year = kwargs.pop('year', None)
        super().__init__(*args, **kwargs)

        if year:
            self.fields['board'].queryset = Board.objects.filter(year=year)
        else:
            self.fields['board'].queryset = Board.objects.none()

    board = forms.ModelChoiceField(
        queryset=Board.objects.none(),  # Will be set in __init__
        label="Board",
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    maths = forms.FloatField(
        label='Maths Mark',
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'min': '0',
            'max': '100',
            'step': '0.01'
        })
    )
    physics = forms.FloatField(
        label='Physics Mark',
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'min': '0',
            'max': '100',
            'step': '0.01'
        })
    )
    chemistry = forms.FloatField(
        label='Chemistry Mark',
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'min': '0',
            'max': '100',
            'step': '0.01'
        })
    )
    entrance = forms.FloatField(
        required=False,
        label='KEAM Entrance Exam Score (out of 300)',
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'min': '0',
            'max': '300',
            'step': '0.01'
        })
    )
