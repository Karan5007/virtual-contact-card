# Use an official Python runtime as a parent image
FROM python:3.8

RUN apt-get update
RUN apt-get -y install nano

# Set the working directory
WORKDIR /app

COPY . /app

# Install any needed packages
RUN pip install --trusted-host pypi.python.org -r requirements.txt

pip install 

# Copy the current directory contents into the container at /app


# Make port 5000 available to the world outside this container
EXPOSE 5000

# Run app.py when the container launches
CMD ["python", "app.py"]
