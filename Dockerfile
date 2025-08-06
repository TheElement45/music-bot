# Use an official Python runtime as a parent image.
FROM python:3.13-slim   

# --- Environment Variables ---
# Prevents Python from writing .pyc files to disc
ENV PYTHONDONTWRITEBYTECODE=1
# Ensures Python output is sent straight to the terminal without being buffered
ENV PYTHONUNBUFFERED=1

# --- System Dependencies ---
# Update the package manager and install FFmpeg, which is required for audio playback.
# Then, clean up the apt cache to keep the image size small.
RUN apt-get update && \
    apt-get upgrade -y  && \
    apt-get install -y ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# --- Application Setup ---
# Set the working directory in the container to /app
WORKDIR /app

# Copy the requirements file into the container at /app
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
# --no-cache-dir ensures we don't store the pip cache, keeping the image smaller.
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application's code from your host to the container's /app directory
COPY . .

# --- Run the Bot ---
# Specify the command to run when the container starts.
CMD ["python", "main.py"]