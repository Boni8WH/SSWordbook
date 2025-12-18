self.addEventListener('install', function (event) {
    self.skipWaiting();
});

self.addEventListener('push', function (event) {
    let data = {};
    if (event.data) {
        data = event.data.json();
    }

    const title = data.title || 'SSWordbook Notification';
    const options = {
        body: data.body || '新しい通知があります',
        icon: self.location.origin + '/static/pergamon/normal_logo.png?v=7',
        badge: self.location.origin + '/static/NapoleonLogo.png?v=7',
        data: {
            url: data.url || '/'
        }
    };

    event.waitUntil(
        self.registration.showNotification(title, options)
    );
});

self.addEventListener('notificationclick', function (event) {
    event.notification.close();
    event.waitUntil(
        clients.openWindow(event.notification.data.url)
    );
});
