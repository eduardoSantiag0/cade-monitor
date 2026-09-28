from datetime import date

from django.test import TestCase

from apps.dou import selectors
from apps.dou.models import DouSendLog, DouSubscription
from apps.subscribers.models import Subscriber


class AlreadySentTest(TestCase):
    def setUp(self):
        subscriber = Subscriber.objects.create(name='Fulano', email='fulano@example.com')
        self.subscription = DouSubscription.objects.create(subscriber=subscriber)

    def test_false_before_any_log(self):
        self.assertFalse(
            selectors.already_sent(self.subscription, DouSendLog.Kind.DIGEST, date(2026, 9, 28))
        )

    def test_true_after_exact_match(self):
        DouSendLog.objects.create(
            subscription=self.subscription, kind=DouSendLog.Kind.DIGEST,
            reference_date=date(2026, 9, 28), status=DouSendLog.Status.SENT,
        )
        self.assertTrue(
            selectors.already_sent(self.subscription, DouSendLog.Kind.DIGEST, date(2026, 9, 28))
        )

    def test_false_for_different_kind_or_date(self):
        DouSendLog.objects.create(
            subscription=self.subscription, kind=DouSendLog.Kind.DIGEST,
            reference_date=date(2026, 9, 28), status=DouSendLog.Status.SENT,
        )
        self.assertFalse(
            selectors.already_sent(self.subscription, DouSendLog.Kind.PUBDOU_ANT, date(2026, 9, 28))
        )
        self.assertFalse(
            selectors.already_sent(self.subscription, DouSendLog.Kind.DIGEST, date(2026, 9, 29))
        )
