document.querySelectorAll('[data-analytics-event]').forEach((link) => {
  link.addEventListener('click', () => {
    if (typeof window.gtag !== 'function') return;

    const eventName = link.dataset.analyticsEvent;
    window.gtag('event', eventName, {
      contact_method: 'email',
    });
  });
});
