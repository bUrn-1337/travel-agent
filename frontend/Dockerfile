FROM nginx:1.27-alpine

COPY index.html          /usr/share/nginx/html/
COPY app.js              /usr/share/nginx/html/
COPY style.css           /usr/share/nginx/html/
COPY auth.js             /usr/share/nginx/html/
COPY destination.html    /usr/share/nginx/html/
COPY destination.css     /usr/share/nginx/html/
COPY destination.js      /usr/share/nginx/html/
COPY trips.html          /usr/share/nginx/html/
COPY trips.js            /usr/share/nginx/html/
COPY trips.css           /usr/share/nginx/html/
COPY trip.html           /usr/share/nginx/html/
COPY trip.js             /usr/share/nginx/html/
COPY trip.css            /usr/share/nginx/html/

# Proxy /api/* to the backend service
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
