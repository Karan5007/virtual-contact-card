#!/bin/bash 
javac LoadTest.java 
echo $SECONDS 
java LoadTest 127.0.0.1 8081 11 GET 1000 &
java LoadTest 127.0.0.1 8081 12 GET 1000 & 
java LoadTest 127.0.0.1 8081 100 GET 1000 & 
java LoadTest 127.0.0.1 8081 101 GET 1000 & 
wait $(jobs -p) 
echo $SECONDS
