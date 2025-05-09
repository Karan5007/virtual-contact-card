#!/bin/bash

# Prepare load test data
NUM_REQUESTS=5000
HOST="127.0.0.1"
PORT=8083
CONCURRENCY=10

# Function to generate a random string of specified length
generate_random_string() {
  local length=$1
  cat /dev/urandom | tr -dc 'a-zA-Z0-9' | fold -w ${length} | head -n 1
}

# Performance testing with ab for PUT requests
echo "Starting performance test for PUT requests..."
START_TIME=$SECONDS

shortResource=$(generate_random_string 20)
longResource="http://$(generate_random_string 100)"
  
request="http://$HOST:$PORT/?short=$shortResource&long=$longResource"
  
# Use ab to perform load test and save results to a .tsv file
ab -n $NUM_REQUESTS -c $CONCURRENCY -g load.tsv -T "application/x-www-form-urlencoded" -p /dev/null "$request" &


# Wait for all background processes to finish
wait $(jobs -p)

echo "PUT request load test completed in $(( SECONDS - START_TIME )) seconds."
