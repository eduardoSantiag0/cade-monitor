from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from .forms import ProcessSubscriptionForm, SubscriberForm
from .models import ProcessSubscription, Subscriber


@login_required
def subscriber_list(request):
    subscribers = Subscriber.objects.prefetch_related('subscriptions__process').all()
    return render(request, 'subscribers/list.html', {'subscribers': subscribers})


@login_required
def subscriber_create(request):
    if request.method == 'POST':
        form = SubscriberForm(request.POST)
        if form.is_valid():
            subscriber = form.save()
            messages.success(request, f'Assinante "{subscriber.name}" cadastrado.')
            return redirect('subscribers:detail', pk=subscriber.pk)
    else:
        form = SubscriberForm()
    return render(request, 'subscribers/form.html', {'form': form, 'title': 'Novo assinante'})


@login_required
def subscriber_detail(request, pk):
    subscriber = get_object_or_404(Subscriber, pk=pk)
    subscriptions = subscriber.subscriptions.select_related('process').all()
    sub_form = ProcessSubscriptionForm()
    return render(request, 'subscribers/detail.html', {
        'subscriber': subscriber,
        'subscriptions': subscriptions,
        'sub_form': sub_form,
    })


@login_required
def subscriber_edit(request, pk):
    subscriber = get_object_or_404(Subscriber, pk=pk)
    if request.method == 'POST':
        form = SubscriberForm(request.POST, instance=subscriber)
        if form.is_valid():
            form.save()
            messages.success(request, 'Assinante atualizado.')
            return redirect('subscribers:detail', pk=subscriber.pk)
    else:
        form = SubscriberForm(instance=subscriber)
    return render(request, 'subscribers/form.html', {
        'form': form,
        'subscriber': subscriber,
        'title': 'Editar assinante',
    })


@login_required
def subscription_add(request, subscriber_pk):
    subscriber = get_object_or_404(Subscriber, pk=subscriber_pk)
    if request.method == 'POST':
        form = ProcessSubscriptionForm(request.POST)
        if form.is_valid():
            sub = form.save(commit=False)
            sub.subscriber = subscriber
            sub.save()
            messages.success(request, f'Assinatura adicionada: {sub.process.label}')
        else:
            messages.error(request, 'Formulário inválido.')
    return redirect('subscribers:detail', pk=subscriber_pk)


@login_required
def subscription_remove(request, pk):
    sub = get_object_or_404(ProcessSubscription, pk=pk)
    subscriber_pk = sub.subscriber_id
    if request.method == 'POST':
        sub.delete()
        messages.success(request, 'Assinatura removida.')
    return redirect('subscribers:detail', pk=subscriber_pk)
