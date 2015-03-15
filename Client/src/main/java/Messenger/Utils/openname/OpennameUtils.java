package Messenger.Utils.openname;

import Messenger.Address;
import Messenger.TorLib;
import org.apache.http.HttpException;
import org.json.JSONException;
import org.json.JSONObject;

import javax.imageio.ImageIO;
import java.awt.*;
import java.awt.image.BufferedImage;
import java.io.*;
import java.net.URL;

/**
 * Class for downloading the openname avatar and saving it to disk
 */
public class OpennameUtils {

    /**
     * Downloads the openname profie while blocking.
     * Saves the avatar to disk and returns the formatted name.
     **/
    public static String blockingOpennameDownload(String openname, String dataFolderPath){
        //I haven't yet figured out how to parse the avatar image from a raw http query response.
        //For now I'm using ImageIO.read() which does not send DNS query over Tor.
        //To allow that we have to set some proxy settings.
        System.getProperties().put( "proxySet", "true" );
        System.getProperties().put( "socksProxyHost", "127.0.0.1" );
        System.getProperties().put( "socksProxyPort", "9150" );
        String formatted = "";
        try {
            JSONObject obj = getOneNameJSON(openname);
            JSONObject avi = obj.getJSONObject("avatar");
            JSONObject name = obj.getJSONObject("name");
            formatted = name.getString("formatted");
            String aviLocation = avi.getString("url");
            URL url = new URL(aviLocation);
            BufferedImage img = cropDownloadedAvatarImage(ImageIO.read(url));
            File outputfile = new File(dataFolderPath + "/avatars/" + openname + ".jpg");
            ImageIO.write(img, "jpg", outputfile);
        } catch (JSONException | IOException | HttpException e) {
            System.getProperties().put( "proxySet", "false" );
            return null;
        }
        //Reset the proxy settings so we don't keep leaking our IP during the DNS query.
        System.getProperties().put( "proxySet", "false" );
        return formatted;
    }

    /**Creates a new thread and downloads the avatar and saves it to disk**/
    public static void downloadAvatar(String openname, String dataFolderPath,
                                      OpennameListener listener, Address addr){
        //I haven't yet figured out how to parse the avatar image from a raw http query response.
        //For now I'm using ImageIO.read() which does not send DNS query over Tor.
        //To allow that we have to set some proxy settings.
        System.getProperties().put( "proxySet", "true" );
        System.getProperties().put( "socksProxyHost", "127.0.0.1" );
        System.getProperties().put( "socksProxyPort", "9150" );
        Runnable task = () -> {
            try {
                JSONObject obj = getOneNameJSON(openname);
                JSONObject avi = obj.getJSONObject("avatar");
                JSONObject name = obj.getJSONObject("name");
                String formattedName = name.getString("formatted");
                String aviLocation = avi.getString("url");
                URL url = new URL(aviLocation);
                BufferedImage img = cropDownloadedAvatarImage(ImageIO.read(url));
                File outputfile = new File(dataFolderPath + "/avatars/" + openname + ".jpg");
                ImageIO.write(img, "jpg", outputfile);
                listener.onDownloadComplete(addr, formattedName);
            } catch (JSONException | IOException | HttpException e) {
                listener.onDownloadFailed();
            }
        };
        Thread t = new Thread(task);
        t.start();
        //Reset the proxy settings so we don't keep leaking our IP during the DNS query.
        System.getProperties().put( "proxySet", "false" );
    }

    /**Download the openname json object over Tor**/
    private static JSONObject getOneNameJSON(String openname) throws JSONException, HttpException, IOException{
        return TorLib.getJSON("bitcoinauthenticator.org",
                    "onename.php?id=" + openname + ".json");
    }

    /**Crop the avatar into a square so it looks better**/
    private static BufferedImage cropDownloadedAvatarImage(BufferedImage image) throws IOException {
        //Scale the image
        int imageWidth = image.getWidth();
        int imageHeight = image.getHeight();
        int width;
        int height;
        if (imageWidth > imageHeight) {
            Double temp = (73 / (double) imageHeight) * (double) imageWidth;
            width = temp.intValue();
            height = 73;
        } else {
            Double temp = (73 / (double) imageWidth) * (double) imageHeight;
            width = 73;
            height = temp.intValue();
        }
        BufferedImage scaledImage = new BufferedImage(width, height, image.getType());
        Graphics2D g = scaledImage.createGraphics();
        g.drawImage(image, 0, 0, width, height, null);
        g.dispose();
        //Crop the image
        int x, y;
        if (width > height) {
            y = 0;
            x = (width - 73) / 2;
        } else {
            x = 0;
            y = (height - 73) / 2;
        }
        return scaledImage.getSubimage(x, y, 73, 73);
    }
}
