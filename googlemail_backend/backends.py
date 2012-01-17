
import re
import datetime
import logging
import cPickle as pickle

from django.conf import settings
from django.core.cache import cache
from django.core.mail import get_connection
#~ from django.core.mail.backends.base import BaseEmailBackend
from django.core.mail.backends.smtp import EmailBackend
from django.db import transaction

from .models import GoogleMailQuota, GoogleMailQuotaRequeue

logger = logging.getLogger("mail.backends.GoogleMailBackend")

# For details on limits/quotas see:
# http://support.google.com/a/bin/answer.py?hl=en&answer=166852
# http://support.google.com/mail/bin/answer.py?hl=en&answer=22839

re_extractor = re.compile(r'.*<(.*)>')
def _extract_email(astr):
    m = re_extractor.match(astr)
    if m:
        return m.group(1)
    return astr


class QuotaException(Exception): pass

"""
class QuotaContextManager(object):
    def __enter__(self):
        raise NotImplementedError()
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        raise NotImplementedError()


class GoogleMailQuotaContextManager(QuotaContextManager):
    RECIPIENTS_PER_DAY = 5 # 
    RECIPIENTS_PER_DAY_UNIQUE = 3 # 
    
    MSG_PER_DAY = 2000
    RECIPIENTS_PER_MSG = 100 # much larger when using web interface
    #~ RECIPIENTS_PER_DAY = 3000 # 
    #~ RECIPIENTS_PER_DAY_UNIQUE = 2000 # 
    
    def __enter__(self):
        raise NotImplementedError()
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        raise NotImplementedError()
"""

class GoogleMailBackend(EmailBackend):
    """
    Django email backend which respects mailing limits as documented by google.
    """
    
    MSG_PER_DAY = 2000
    RECIPIENTS_PER_MSG = 100 # much larger when using web interface
    RECIPIENTS_PER_DAY = 3000 # 
    RECIPIENTS_PER_DAY_UNIQUE = 2000 # 
    
    def __init__(self, *args, **kwargs):
        super(GoogleMailBackend, self).__init__(*args, **kwargs)
        self._requeue_send_date = datetime.date.today()
    
    # Roll up in a transaction so that two seperate processes won't be able
    # to exceed the quotas.
    @transaction.commit_on_success
    def _send(self, email_message):
        # Allow messages that failed to send because of a quota exception
        # to be queued for resending the following day.
        EMAIL_GOOGLEMAIL_REQUEUE = getattr(settings, 'EMAIL_GOOGLEMAIL_REQUEUE', False)
        # Allow queued messages to be split into several emails to more
        # efficiently utilize quotas (potentially danergous)
        EMAIL_GOOGLEMAIL_REQUEUE_SPLIT_MSG = getattr(settings, 'EMAIL_GOOGLEMAIL_REQUEUE_SPLIT_MSG', False)
        # Send all emails to EMAIL_GOOGLEMAIL_TEST_ACCOUNT for testing purposes.
        EMAIL_GOOGLEMAIL_TEST_ACCOUNT = getattr(settings, 'EMAIL_GOOGLEMAIL_TEST_ACCOUNT', None)
        
        # Should we should send to a test account?
        if EMAIL_GOOGLEMAIL_TEST_ACCOUNT:
            
            # Prepend to whom the email is addressed to the body and send
            # to the test account
            prepend_body = "To: {}\n".format(email_message.to)
            email_message.to = [EMAIL_GOOGLEMAIL_TEST_ACCOUNT]
            if email_message.cc:
                prepend_body += "CC: {}\n".format(email_message.cc)
                email_message.cc = []
            if email_message.bcc:
                prepend_body += "BCC: {}\n".format(email_message.bcc)
                email_message.bcc = []
            
            email_message.body = prepend_body + email_message.body
            
            return super(GoogleMailBackend, self)._send(email_message)
        
        # Only try resending from queue once a day (preferrably first thing)
        if EMAIL_GOOGLEMAIL_REQUEUE and self._requeue_send_date < datetime.date.today():
            # This is only partially implemented. It needs more thought...
            raise NotImplemented()
            
            # If there are any queued emails that need to be sent, try
            # sending them now.
            for gmqr in GoogleMailQuotaRequeue.objects.all():
                message = pickle.loads(gmqr.object)
                
                # Should we resend via this backend or the global one?
                #~ sent = self.send_message([message]) # current backend
                sent = message.send(fail_silently=True) # global backend
                
                # Message was successfully, so delete the queue item
                if sent:
                    gmqr.delete()
            
            self._requeue_send_date = datetime.date.today()
        
        recipients = email_message.recipients()
        len_recipients = len(recipients)
        if len_recipients > self.RECIPIENTS_PER_MSG:
            if self.fail_silently:
                return
            raise QuotaException("Maximum recipients exceeded: %d allowed "
                                 "but %d set in message" % (self.RECIPIENTS_PER_MSG, len(recipients)))
        
        cache_key = __name__+'.GoogleMailQuota'
        gmrec = cache.get(cache_key)
        if gmrec is None:
            try:
                gmrec = GoogleMailQuota.objects.filter(date=datetime.date.today()).get()
            except GoogleMailQuota.DoesNotExist, e:
                gmrec = GoogleMailQuota()
            cache.set(cache_key, gmrec)
        
        # TODO: Turn this into a context manager like:
        # with QuotaCM() as ctx:
        #     if ctx.allow():
        #         ... send email ...
        #         ctx.sent = did_send
        try:
            total_recipients = self._check_quota_exception(email_message, gmrec)
        except QuotaException, e:
            logger.info(e.message)
            if EMAIL_GOOGLEMAIL_REQUEUE:
                GoogleMailQuotaRequeue(object=pickle.dumps(email_message)).save()
                # Let's lie and say we sent it, since it should get sent later
                #~ return True
                return False
            else:
                raise
        
        did_send = super(GoogleMailBackend, self)._send(email_message)
        #~ did_send = True
        
        # If we successfully sent the email, then update the database to
        # reflect used quota.
        if did_send:
            gmrec.sent += 1
            gmrec.recipients = ','.join(total_recipients)
            gmrec.save()
            cache.set(cache_key, gmrec)
        
        return did_send
    
    def _check_quota_exception(self, email_message, quota_record):
        recipients = email_message.recipients()
        len_recipients = len(recipients)
        
        if (quota_record.sent + 1) > self.MSG_PER_DAY:
            raise QuotaException("Messages per day quota exceeded: already "
                                 "sent %d messages." % quota_record.sent)
        
        # make sure to set sent_recipients to the empty list if recipients is
        # the empty string because ''.split(',') == ['']
        sent_recipients = quota_record.recipients.split(',') if quota_record.recipients else []
        len_sent_recipients = len(sent_recipients)
        if (len_sent_recipients + len_recipients) > self.RECIPIENTS_PER_DAY:
            raise QuotaException("Recipients per day quota exceeded: already "
                                 "sent to %d recipients and trying to send to "
                                 "%d more." % (len_sent_recipients, len_recipients))
        
        # Make sure we're just getting the email addresses in case the
        # "Some Name" <email@q.com> format is used. This allows us to truly
        # get the unique recipients.
        recipients = map(_extract_email, recipients)
        sent_recipients_set = set(sent_recipients)
        unique_recipients = set(recipients)
        unique_recipients.update(sent_recipients_set)
        if len(unique_recipients) > self.RECIPIENTS_PER_DAY_UNIQUE:
            raise QuotaException("Unique recipients per day quota exceeded: "
                                 "already sent to %d unique recipients." % len(unique_recipients))
        
        return sent_recipients + recipients

