document.querySelectorAll('[data-analytics-event]').forEach((link) => {
  link.addEventListener('click', (clickEvent) => {
    if (typeof window.gtag !== 'function') return;

    const eventName = link.dataset.analyticsEvent;
    if (eventName === 'feed_open' || eventName === 'grind_chart_open') {
      const opensCurrentTab = clickEvent.button === 0
        && !clickEvent.metaKey
        && !clickEvent.ctrlKey
        && !clickEvent.shiftKey
        && !clickEvent.altKey
        && (!link.target || link.target === '_self');

      if (!opensCurrentTab) {
        window.gtag('event', eventName);
        return;
      }

      clickEvent.preventDefault();
      let followed = false;
      const followFeed = () => {
        if (followed) return;
        followed = true;
        window.location.assign(link.href);
      };
      window.gtag('event', eventName, {
        event_callback: followFeed,
        transport_type: 'beacon',
      });
      window.setTimeout(followFeed, 500);
      return;
    }

    if (eventName === 'affiliate_click') {
      const opensCurrentTab = clickEvent.button === 0
        && !clickEvent.metaKey
        && !clickEvent.ctrlKey
        && !clickEvent.shiftKey
        && !clickEvent.altKey
        && (!link.target || link.target === '_self');

      if (!opensCurrentTab) {
        window.gtag('event', eventName, {
          affiliate_partner: link.dataset.affiliatePartner,
          affiliate_placement: link.dataset.affiliatePlacement,
        });
        return;
      }

      clickEvent.preventDefault();
      let followed = false;
      const followAffiliate = () => {
        if (followed) return;
        followed = true;
        window.location.assign(link.href);
      };
      window.gtag('event', eventName, {
        affiliate_partner: link.dataset.affiliatePartner,
        affiliate_placement: link.dataset.affiliatePlacement,
        event_callback: followAffiliate,
        transport_type: 'beacon',
      });
      window.setTimeout(followAffiliate, 500);
      return;
    }

    window.gtag('event', eventName, {
      contact_method: 'email',
      inquiry_type: link.dataset.inquiryType || 'general',
    });
  });
});
