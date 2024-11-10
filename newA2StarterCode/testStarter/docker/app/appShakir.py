from flask import Flask, request, redirect, jsonify
# import redis
from redis import Redis, RedisError
from cassandra.cluster import Cluster
from cassandra.query import SimpleStatement

app = Flask(__name__)

# Connect to Redis (pointing to primary)
# redis_client = redis.Redis(host='redis-primary', port=6379, decode_responses=True)
redis_master = Redis(host="redis-master", port=6379, db=0, socket_connect_timeout=2, socket_timeout=2, decode_responses=True)
redis_slaves = [
    Redis(host="redis-slave", port=6380, db=0, socket_connect_timeout=2, socket_timeout=2, decode_responses=True)
]
# print(f"Redis Client Initialized: {redis_client}")  # Debug print
# Function to randomly choose a Redis slave
def get_slave_connection():
    return random.choice(redis_slaves)

print(f"Redis Master Client Initialized: {redis_master}")  # Debug print
print(f"Redis Slave Clients Initialized: {redis_slaves}")   # Debug print
# Connect to Cassandra cluster
# cluster = Cluster(['cassandra-seed', 'cassandra-node-2', 'cassandra-node-3'])
#cluster = Cluster(['10.128.2.90', '10.128.3.90', '10.128.4.90'])
# cluster = Cluster(['10.128.2.90'])
cluster = Cluster(['10.128.2.114', '10.128.3.114', '10.128.4.114'])
session = cluster.connect()
session.execute("CREATE KEYSPACE IF NOT EXISTS url_shortener WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 2}")
session.set_keyspace("url_shortener")
session.execute("""
    CREATE TABLE IF NOT EXISTS urls (
        shorturl text PRIMARY KEY,
        longurl text,
        last_updated timestamp
    )
""")

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy"}), 200

@app.route('/shorturl', methods=['GET'])
def get_short_url():
    shorturl = request.args.get('shorturl')
    if not shorturl:
        return jsonify({"error": "shorturl parameter missing"}), 400

    # First check Redis
    slave = get_slave_connection()

    longurl = slave.get(shorturl)
    if longurl:
        return redirect(longurl)  # Redirect if found in cache

    # Check Cassandra if not in Redis
    query = "SELECT longurl FROM urls WHERE shorturl = %s"
    result = session.execute(SimpleStatement(query), (shorturl,))
    row = result.one()
    if row:
        longurl = row.longurl
        redis_master.set(shorturl, longurl)  # Cache in Redis
        return redirect(longurl)

    return jsonify({"error": "URL not found"}), 404

@app.route('/shorturl', methods=['PUT'])
def put_short_url():
    data = request.json
    shorturl = data.get('shorturl')
    longurl = data.get('longurl')
    if not shorturl or not longurl:
        return jsonify({"error": "shorturl and longurl required"}), 400

    # Use the current timestamp
    current_timestamp = datetime.utcnow()

    # Write to Cassandra
    query = "INSERT INTO urls (shorturl, longurl, last_updated) VALUES (%s, %s, %s)"
    statement = SimpleStatement(query, consistency_level=ConsistencyLevel.QUORUM)
    session.execute(SimpleStatement(query), (shorturl, longurl))

    # Update Redis cache
    slave = get_slave_connection()

    cached_data = slave.hgetall(shorturl)
    if cached_data:
        cached_timestamp = datetime.strptime(cached_data['last_updated'], "%Y-%m-%d %H:%M:%S.%f")
        if current_timestamp > cached_timestamp:
            # Update cache if this write is more recent
            redis_master.hmset(shorturl, {"longurl": longurl, "last_updated": current_timestamp.isoformat()})
    else:
        # No cached entry, so add it
        redis_master.hmset(shorturl, {"longurl": longurl, "last_updated": current_timestamp.isoformat()})
    return jsonify({"message": "URL added"}), 201

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80)