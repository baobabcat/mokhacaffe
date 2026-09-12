import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const source = fs.readFileSync(new URL('../public/assets/analytics-events.js', import.meta.url), 'utf8');

function loadLink(dataset) {
  let handler;
  const calls = [];
  const navigations = [];
  const timers = [];
  const link = {
    dataset,
    href: 'https://mokhacaffe.com/feed.xml',
    target: '',
    addEventListener(name, callback) {
      assert.equal(name, 'click');
      handler = callback;
    },
  };
  const window = {
    gtag(...args) { calls.push(args); },
    location: { assign(url) { navigations.push(url); } },
    setTimeout(callback, delay) { timers.push({ callback, delay }); },
  };
  vm.runInNewContext(source, {
    document: { querySelectorAll() { return [link]; } },
    window,
  });
  return { handler, calls, navigations, timers };
}

{
  const state = loadLink({ analyticsEvent: 'feed_open' });
  let prevented = false;
  state.handler({
    button: 0,
    metaKey: false,
    ctrlKey: false,
    shiftKey: false,
    altKey: false,
    preventDefault() { prevented = true; },
  });
  assert.equal(prevented, true);
  assert.equal(state.navigations.length, 0);
  assert.equal(state.calls.length, 1);
  assert.equal(state.calls[0][0], 'event');
  assert.equal(state.calls[0][1], 'feed_open');
  assert.equal(typeof state.calls[0][2].event_callback, 'function');
  assert.equal(state.calls[0][2].transport_type, 'beacon');
  assert.deepEqual(Object.keys(state.calls[0][2]).sort(), ['event_callback', 'transport_type']);
  assert.equal(state.timers.length, 1);
  assert.equal(state.timers[0].delay, 500);
  state.calls[0][2].event_callback();
  assert.deepEqual(state.navigations, ['https://mokhacaffe.com/feed.xml']);
  state.timers[0].callback();
  assert.equal(state.navigations.length, 1);
}

{
  const state = loadLink({ analyticsEvent: 'contact_intent', inquiryType: 'wholesale' });
  state.handler({ button: 0, metaKey: false, ctrlKey: false, shiftKey: false, altKey: false });
  assert.equal(state.calls[0][0], 'event');
  assert.equal(state.calls[0][1], 'contact_intent');
  assert.equal(state.calls[0][2].contact_method, 'email');
  assert.equal(state.calls[0][2].inquiry_type, 'wholesale');
  assert.deepEqual(Object.keys(state.calls[0][2]).sort(), ['contact_method', 'inquiry_type']);
}

console.log('feed and contact analytics behavior passed');
