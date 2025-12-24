# Using official Python runtime as a parent image
FROM python:3.8-slim-buster

# Working directory to /app
WORKDIR /app

# Copies the rest of your code to the working directory in the Docker container
COPY ./app /app
COPY ./requirements.txt /app
COPY ./data /app/data


# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Command to run on container start
CMD ["tail", "-f", "/dev/null"]