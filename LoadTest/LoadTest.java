import java.net.http.*;
import java.net.*;
import java.util.Random;

// https://openjdk.org/groups/net/httpclient/intro.html
// https://openjdk.org/groups/net/httpclient/recipes.html
// https://www.appsdeveloperblog.com/execute-an-http-put-request-in-java/

public class LoadTest {
	static char [] ALPHANUMERIC = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789".toCharArray();
	static Random rand;

	public static String randomString(int length){
		StringBuilder r = new StringBuilder();
		for(int i=0;i<length;i++){
			int index = rand.nextInt(ALPHANUMERIC.length);
			r.append(ALPHANUMERIC[index]);
		}
		return r.toString();
	}
	public static void main(String [] args){
		if(args.length!=5){
			System.out.println("usage: java LoadTest HOST PORT SEED [PUT|GET] NUM_REQUESTS");
			System.exit(1);
		}
		String host = args[0];
		int port = Integer.parseInt(args[1]);
		int seed = Integer.parseInt(args[2]);
		String requestType = args[3];
		int numRequests = Integer.parseInt(args[4]);

		rand = new Random(seed);

		try {
			for(int i=0;i<numRequests;i++){
				String longURL = "http://"+randomString(50);
				String shortURL = randomString(20);
				if(requestType.equals("PUT")){
					put("http://"+host+":"+port+"/?short="+shortURL+"&long="+longURL);
				} 
				if(requestType.equals("GET")){
					get("http://"+host+":"+port+"/"+shortURL);
				} 
				// get("http://mcs.utm.utoronto.ca");
				// get("http://localhost:8080/89M6VVVP7369R1VEPSP0");
			}
		} catch (Exception e){
			e.printStackTrace();
		}
	}

	public static void put(String uri) throws Exception {
	    HttpClient client = HttpClient.newHttpClient();
	    HttpRequest request = HttpRequest.newBuilder()
	          .uri(URI.create(uri))
		  .PUT(HttpRequest.BodyPublishers.noBody())
	          .build();
	
	    HttpResponse<String> response =
	          client.send(request, HttpResponse.BodyHandlers.ofString());
	    System.out.println(response.body());
	    client.close();
	}
	public static void get(String uri) throws Exception {
	    HttpClient client = HttpClient.newHttpClient();
	    HttpRequest request = HttpRequest.newBuilder()
	          .uri(URI.create(uri))
		  .GET()
	          .build();
	
	    HttpResponse<String> response =
	          client.send(request, HttpResponse.BodyHandlers.ofString());
	    client.close();
	
	    System.out.println(response.body());
	}
}
