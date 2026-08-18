(() => {
  'use strict';

  // Only approved DEV hosts expose the private backoffice entrypoint.
  const approvedHosts = new Map([
    ['tpi.localhost', 'backoffice.tpi.localhost'],
    ['tpi-dev-lab.com', 'backoffice.tpi-dev-lab.com'],
  ]);

  const link = document.querySelector('[data-backoffice-access]');
  const backofficeHost = approvedHosts.get(window.location.hostname.toLowerCase());

  if (!link || !backofficeHost) {
    link?.remove();
    return;
  }

  const destination = new URL(window.location.href);
  destination.hostname = backofficeHost;
  destination.port = window.location.port;
  destination.pathname = '/';
  destination.search = '';
  destination.hash = '';

  link.href = destination.toString();
  link.hidden = false;
})();
