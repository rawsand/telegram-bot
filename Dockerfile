# Use official PHP CLI image
FROM php:8.1-cli

# Copy all bot files to /app inside container
COPY . /app

# Set working directory to /app
WORKDIR /app

# Expose port 10000 for PHP built-in server
EXPOSE 10000

# Start PHP built-in server on port 10000
CMD ["php", "-S", "0.0.0.0:10000", "-t", "/app"]
