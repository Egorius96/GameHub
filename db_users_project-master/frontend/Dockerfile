FROM nginx:alpine

# Copy the static files
COPY public/ /usr/share/nginx/html/

# Expose port 3000
EXPOSE 3000

# Update nginx config to listen on port 3000
RUN sed -i 's/listen\(.*\)80;/listen\1 3000;/' /etc/nginx/conf.d/default.conf 