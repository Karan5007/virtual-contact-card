#!/bin/bash 
javac LoadTest.java 
echo $SECONDS 
java LoadTest 127.0.0.1 4000 11 PUT 1000 &
java LoadTest 127.0.0.1 4000 12 PUT 1000 & 
java LoadTest 127.0.0.1 4000 13 PUT 1000 & 
java LoadTest 127.0.0.1 4000 14 PUT 1000 & 
wait $(jobs -p) 
echo $SECONDS
