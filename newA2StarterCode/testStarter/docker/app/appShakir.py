from flask import Flask, request, redirect, jsonify
from redis import Redis, RedisError
from cassandra.cluster import Cluster
from cassandra.query import SimpleStatement
from cassandra import ConsistencyLevel
from datetime import datetime
from cassandra import OperationTimedOut
from collections import deque
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)

redis_master = Redis(host="redis-master", port=6379, db=0, socket_connect_timeout=2, socket_timeout=2, decode_responses=True)
redis_slave = Redis(host="redis-slave", port=6380, db=0, socket_connect_timeout=2, socket_timeout=2, decode_responses=True)
retry_queue = deque()

logging.info("Redis Master Client Initialized: %s", redis_master)
logging.info("Redis Slave Client Initialized: %s", redis_slave)


def initialize_cassandra_connection():
    try:
        # Connect to Cassandra cluster
        cluster = Cluster(['10.128.2.116', '10.128.3.116', '10.128.4.116'])
        session = cluster.connect()
        
        # Create keyspace if not exists
        session.execute("CREATE KEYSPACE IF NOT EXISTS url_shortener WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 2}")
        session.set_keyspace("url_shortener")
        
        # Create table if not exists
        session.execute("""
            CREATE TABLE IF NOT EXISTS urls (
                shorturl text PRIMARY KEY,
                longurl text,
                last_updated timestamp
            )
        """)
        logging.info("Cassandra connection and setup successful.")
        return session  # Return the session to use in other parts of the app
    except OperationTimedOut as e:
        logging.error("Connection to Cassandra cluster timed out: %s", e)
    except Exception as e:
        logging.error("Error connecting to Cassandra: %s", e)
    return None  # Return None if the connection fails
    
session = initialize_cassandra_connection()

def process_retry_queue():
    while retry_queue:
        shorturl, longurl, current_timestamp = retry_queue.popleft()
        try:
            # Write to Cassandra
            query = "INSERT INTO urls (shorturl, longurl, last_updated) VALUES (%s, %s, %s)"
            statement = SimpleStatement(query, consistency_level=ConsistencyLevel.QUORUM)
            session.execute(statement, (shorturl, longurl, current_timestamp))
            logging.info("Inserted (%s, %s) into Cassandra.", shorturl, longurl)

            # Update Redis after successful Cassandra insertion
            try:
                cached_data = redis_slave.hgetall(shorturl)
                if cached_data:
                    cached_timestamp = datetime.fromisoformat(cached_data['last_updated'])
                    if current_timestamp > cached_timestamp:
                        # Update cache if this write is more recent
                        redis_master.hmset(shorturl, {"longurl": longurl, "last_updated": current_timestamp.isoformat()})
                else:
                    # No cached entry, so add it
                    redis_master.hmset(shorturl, {"longurl": longurl, "last_updated": current_timestamp.isoformat()})
            except RedisError as e:
                logging.error("Error updating Redis: %s", e)
                
        except Exception as e:
            logging.error("Error inserting (%s, %s) into Cassandra: %s", shorturl, longurl, e)
            # Add the item to retry queue in case of failure
            retry_queue.append((shorturl, longurl, current_timestamp))
            return False  
    return True

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy"}), 200

@app.route('/<shorturl>', methods=['GET'])
def get_short_url(shorturl):
    global session
    if not shorturl:
        return jsonify({"error": "shorturl parameter missing"}), 404
    longurl = None
    try:
        longurl = redis_slave.get(shorturl)
    except RedisError as e:
        logging.error("Error using Redis: %s", e)
    finally:
        if longurl:
            return redirect(longurl, code=307) # Redirect if found in cache
        # Check Cassandra if not in Redis or Redis is down
        # Check if Cassandra is up
        processedQueue = False
        if session is None:
            session = initialize_cassandra_connection()
        if session is not None:
            processedQueue = process_retry_queue()
        if not processedQueue:
            return jsonify({"error": "URL not found in cache"}), 404

        query = "SELECT longurl FROM urls WHERE shorturl = %s"
        result = session.execute(SimpleStatement(query), (shorturl,))
        row = result.one()
        if row:
            longurl = row.longurl
            try:
                redis_master.set(shorturl, longurl)  # Cache in Redis
            except RedisError as e:
                logging.error("Error using Redis: %s", e)
            return redirect(longurl, code=307)

        return jsonify({"error": "URL not found"}), 404

@app.route('/', methods=['PUT'])
def put_short_url():
    global session
    shorturl = request.args.get('short')
    longurl = request.args.get('long')
    if not shorturl or not longurl:
        return jsonify({"error": "shorturl and longurl required"}), 400

    # Use the current timestamp
    current_timestamp = datetime.utcnow()
    processedQueue = False
    if session is None:
        session = initialize_cassandra_connection()
    if session is not None:
        processedQueue = process_retry_queue()
    if not processedQueue:
        retry_queue.append((shorturl, longurl, current_timestamp))
    else:
        # Write to Cassandra
        query = "INSERT INTO urls (shorturl, longurl, last_updated) VALUES (%s, %s, %s)"
        statement = SimpleStatement(query, consistency_level=ConsistencyLevel.QUORUM)
        session.execute(statement, (shorturl, longurl, current_timestamp))

    try:
        cached_data = redis_slave.hgetall(shorturl)
        if cached_data:
            cached_timestamp = datetime.fromisoformat(cached_data['last_updated'])
            if current_timestamp > cached_timestamp:
                # Update cache if this write is more recent
                redis_master.hmset(shorturl, {"longurl": longurl, "last_updated": current_timestamp.isoformat()})
        else:
            # No cached entry, so add it
            redis_master.hmset(shorturl, {"longurl": longurl, "last_updated": current_timestamp.isoformat()})
    except RedisError as e:
        logging.error("Error using Redis: %s", e)
    return jsonify({"message": "URL added"}), 201

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80)