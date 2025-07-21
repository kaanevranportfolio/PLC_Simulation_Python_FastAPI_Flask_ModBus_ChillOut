FROM nginx:alpine

# Copy nginx configuration
COPY nginx.conf /etc/nginx/nginx.conf

# Copy static files
COPY src/ /usr/share/nginx/html/

# Expose port
EXPOSE 80

# Start nginx
CMD ["nginx", "-g", "daemon off;"]