
from django.db import models
from django.utils.translation import ugettext, ugettext_lazy as _


from django.conf import settings
def get_default_account():
    user = getattr(settings, 'EMAIL_HOST_USER', 'defaultuser')
    host = getattr(settings, 'EMAIL_HOST', 'defaulthost')
    return '{}|{}'.format(user, host)

# NOTE: We may want to have quota have a many-to-many to reipient records
#       so that the database can calculate and verify uniqueness, as opposed
#       to the code doing it.  This may be faster (or not).
#~ class GoogleMailQuotaRecipients(models.Model):
    #~ email = models.CharField(_('email'), max_length=50)


class GoogleMailQuota(models.Model):
    account = models.CharField(_('account'), max_length=50, default=get_default_account)
    date = models.DateField(_("date"), auto_now_add=True, unique=True)
    sent = models.PositiveSmallIntegerField(_("sent"), default=0)
    recipients = models.TextField(_('recipients'))
    #~ recipients = models.ManyToManyField(GoogleMailQuotaRecipients)
    
    def __unicode__(self):
        date_format = u'l, %s' % ugettext("DATE_FORMAT")
        return ugettext('%(date)s sent:%(sent)s account:%(account)s') % {
            'account': self.account,
            #~ 'date': datetime.date(self.date, date_format),
            'date': self.date.isoformat(),
            'sent': self.sent,
        }


class GoogleMailQuotaRequeue(models.Model):
    account = models.CharField(_('account'), max_length=50, default=get_default_account)
    object = models.TextField(_('object'))
    

