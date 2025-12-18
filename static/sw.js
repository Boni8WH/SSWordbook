self.addEventListener('install', function (event) {
    self.skipWaiting();
});


self.addEventListener('fetch', function (event) {
    // Basic pass-through to satisfy PWA requirements
    // In a full offline-first app, caching logic would go here.
});

self.addEventListener('push', function (event) {
    let data = {};
    if (event.data) {
        data = event.data.json();
    }

    const title = data.title || 'SSWordbook Notification';
    const options = {
        body: data.body || '新しい通知があります',
        icon: 'https://upload.wikimedia.org/wikipedia/commons/thumb/5/50/Jacques-Louis_David_-_The_Emperor_Napoleon_in_His_Study_at_the_Tuileries_-_Google_Art_Project.jpg/512px-Jacques-Louis_David_-_The_Emperor_Napoleon_in_His_Study_at_the_Tuileries_-_Google_Art_Project.jpg',
        badge: 'https://sswordbook.onrender.com/static/NapoleonLogo.png?v=8',
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
