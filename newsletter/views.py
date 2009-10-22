import logging

from datetime import datetime

from django.template import RequestContext

from django.shortcuts import get_object_or_404, get_list_or_404, render_to_response
from django.http import HttpResponseRedirect, HttpResponse, Http404

from django.views.generic.list_detail import object_list, object_detail
from django.views.generic.date_based import archive_index

from django.contrib.sites.models import Site
from django.contrib.auth.decorators import login_required

from django.utils.translation import ugettext as _

from newsletter.models import *
from newsletter.forms import *

def newsletter_list(request):
    newsletters = Newsletter.on_site.filter(visible=True)

    if not newsletters:
        raise Http404

    return object_list(request, newsletters, context_instance=RequestContext(request))

def newsletter_detail(request, newsletter_slug):
    newsletters = Newsletter.on_site.filter(visible=True)
    
    if not newsletters:
        raise Http404
        
    return object_detail(request, newsletters, slug=newsletter_slug, context_instance=RequestContext(request))

@login_required
def subscribe_user(request, newsletter_slug):
    my_newsletter = get_object_or_404(Newsletter.on_site, slug=newsletter_slug)
    
    already_subscribed = False
    instance = Subscription.objects.get_or_create(newsletter=my_newsletter, user=request.user)[0]
    
    if instance.activated:
        already_subscribed = True
    elif request.method == 'POST':
        instance.activated = True
        instance.save()
        
        request.user.message_set.create(message=_('You have been subscribed to %s.') % my_newsletter)        
        logging.debug(_('User %s subscribed to %s.') % (request.user, my_newsletter))

    if already_subscribed:
        request.user.message_set.create(message=_('You are already subscribed to %s.') % my_newsletter) 
        
    env = { 'newsletter'            : my_newsletter,
            'action'                : 'subscribe',}
    
    return render_to_response("newsletter/subscription_subscribe_user.html", env, context_instance=RequestContext(request))    
        

@login_required
def unsubscribe_user(request, newsletter_slug):
    my_newsletter = get_object_or_404(Newsletter.on_site, slug=newsletter_slug)
    
    not_subscribed = False
    
    try:
        instance = Subscription.objects.get(newsletter=my_newsletter, user=request.user)
        if not instance.activated:
            not_subscribed = True
        elif request.method == 'POST':
            instance.activated=False
            instance.save()
        
            request.user.message_set.create(message=_('You have been unsubscribed from %s.') % my_newsletter)        
            logging.debug(_('User %s unsubscribed from %s.') % (request.user, my_newsletter))
        
    except Subscription.DoesNotExist:
        not_subscribed = True
    
    if not_subscribed:
        request.user.message_set.create(message=_('You are not subscribed to %s.') % my_newsletter)         
    
    env = { 'newsletter'     : my_newsletter,
            'action'         : 'unsubscribe' }
    
    return render_to_response("newsletter/subscription_unsubscribe_user.html", env, context_instance=RequestContext(request))     
    
def subscribe_request(request, newsletter_slug):
    my_newsletter = get_object_or_404(Newsletter.on_site, slug=newsletter_slug)
    
    error = None
    if request.POST:
        form = SubscribeRequestForm(request.POST, newsletter=my_newsletter, ip=request.META.get('REMOTE_ADDR'))
        if form.is_valid():
            instance = form.save()
            
            try:
                instance.send_activation_email(action='subscribe')
            except Exception, e:
                logging.warn('Error %s while submitting email to %s.' % (e, instance.email))
                error = True
    else:
        form = SubscribeRequestForm(newsletter=my_newsletter)
    
    env = { 'newsletter' : my_newsletter,
            'form' : form,
            'error' : error,
            'action' :'subscribe' }
    
    return render_to_response("newsletter/subscription_subscribe.html", env, context_instance=RequestContext(request))
    
def unsubscribe_request(request, newsletter_slug):
    my_newsletter = get_object_or_404(Newsletter.on_site, slug=newsletter_slug)
    
    error = None
    if request.POST:
        form = UnsubscribeRequestForm(request.POST, newsletter=my_newsletter)
        if form.is_valid():
            instance = form.instance
            try:
                instance.send_activation_email(action='unsubscribe')
            except Exception, e:
                logging.warn('Error %s while submitting email to %s.' % (e, instance.email))
                error = True
    else:
        form = UnsubscribeRequestForm(newsletter=my_newsletter)
    
    env = { 'newsletter' : my_newsletter,
            'form' : form,
            'error' : error,
            'action' :'unsubscribe' }
            
    return render_to_response("newsletter/subscription_unsubscribe.html", env, context_instance=RequestContext(request))

def update_request(request, newsletter_slug):
    my_newsletter = get_object_or_404(Newsletter.on_site, slug=newsletter_slug)
    
    error = None
    if request.POST:
        form = UpdateRequestForm(request.POST, newsletter=my_newsletter)
        if form.is_valid():
            instance = form.instance
            try:
                instance.send_activation_email(action='update')
            except Exception, e:
                logging.warn('Error %s while submitting email to %s.' % (e, instance.email))
                error = True
    else:
        form = UpdateRequestForm(newsletter=my_newsletter)

    env = { 'newsletter' : my_newsletter,
            'form' : form,
            'error' : error,
            'action' :'update' }
            
    return render_to_response("newsletter/subscription_update.html", env, context_instance=RequestContext(request))


def update_subscription(request, newsletter_slug, email, action, activation_code=None):
    if not action in ['subscribe', 'update', 'unsubscribe']:
        raise Http404
    
    my_newsletter = get_object_or_404(Newsletter.on_site, slug=newsletter_slug)
    my_subscription = get_object_or_404(Subscription, newsletter=my_newsletter, email_field__exact=email)
    
    if activation_code:
        my_initial = {'user_activation_code' : activation_code}
    else:
        my_initial = None
    
    if request.POST:
        form = UpdateForm(request.POST, newsletter=my_newsletter, instance=my_subscription, initial=my_initial)
        if form.is_valid():
            # Get our instance, but do not save yet
            subscription = form.save(commit=False)
            
            # If a new subscription or update, make sure it is activated
            # Else, unsubscribe
            if action == 'subscribe' or action == 'update':
                subscription.activated=True
            else:
                subscription.unsubscribed=True
                subscription.unsubscribe_date = datetime.now()
            
            logging.debug(_(u'Updated subscription %(subscription)s through the web.') % {'subscription':subscription})
            subscription.save()
    else:
        form = UpdateForm(newsletter=my_newsletter, instance=my_subscription, initial=my_initial)
        
        # If we are activating and activation code is valid and not already activated, activate straight away
        # if action == 'subscribe' and form.is_valid() and not my_subscription.activated:
        #     subscription = form.save(commit=False)
        #     subscription.activated = True
        #     subscription.save()
        #     
        #     logging.debug(_(u'Activated subscription %(subscription)s through the web.') % {'subscription':subscription})
        # from ipdb import set_trace; set_trace()
            
    env = { 'newsletter' : my_newsletter,
            'form' : form,
            'action' : action }
    
    return render_to_response("newsletter/subscription_activate.html", env, context_instance=RequestContext(request))

def archive(request, newsletter_slug):
    my_newsletter = get_object_or_404(Newsletter.on_site, slug=newsletter_slug)
    
    publications = Mailing.objects.filter(newsletter = my_newsletter)
    
    return archive_index(request, publications, 'publish_date', extra_context = {'newsletter': my_newsletter}, context_instance=RequestContext(request))