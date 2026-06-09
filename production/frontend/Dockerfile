# Use official Nginx lightweight image
FROM nginx:alpine

# Copy the static HTML file to the Nginx default public directory
COPY index.html /usr/share/nginx/html/index.html

# Copy static assets (logo, etc.)
COPY assets/ /usr/share/nginx/html/assets/

# Expose port 80 inside the container
EXPOSE 80