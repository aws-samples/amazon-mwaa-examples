// Main lambda function
import { Handler } from "aws-lambda";
import { MWAAClient, CreateWebLoginTokenCommand } from "@aws-sdk/client-mwaa";
import * as process from "process";

const MWAA_ENDPOINT: string = process.env.MWAA_ENDPOINT || "";
const MWAA_NAME: string = process.env.MWAA_NAME || "";
const MWAA_REGION: string = process.env.MWAA_REGION || "us-east-1";

console.info(
  `MWAA Endpoint: ${MWAA_ENDPOINT}, Name: ${MWAA_NAME}, Region: ${MWAA_REGION}`,
);

function getMwaaClient(): MWAAClient | null {
  try {
    const mwaa = new MWAAClient({ region: MWAA_REGION });
    return mwaa;
  } catch (error) {
    console.error(`Error creating MWAA client: ${error}`);
    return null;
  }
}

async function login(headers: { [key: string]: string[] }): Promise<{
  statusCode: number;
  statusDescription: string;
  multiValueHeaders?: { [key: string]: string[] };
}> {
  const host = headers["host"][0];
  const mwaa = getMwaaClient();
  if (mwaa) {
    try {
      const command = new CreateWebLoginTokenCommand({ Name: MWAA_NAME });
      const mwaaWebTokenResponse = await mwaa.send(command);
      console.info("Redirecting with Amazon MWAA WEB TOKEN");
      return {
        statusCode: 302,
        statusDescription: "302 Found",
        multiValueHeaders: {
          Location: [
            `https://${host}/aws_mwaa/aws-console-sso?login=true#${mwaaWebTokenResponse.WebToken}`,
          ],
        },
      };
    } catch (error) {
      return {
        statusCode: 302,
        statusDescription: `Error ${error}`,
      };
    }
  } else {
    return {
      statusCode: 302,
      statusDescription: "No valid MWAA",
    };
  }
}

export const handler: Handler = async (event, context) => {
  console.log("EVENT: \n" + JSON.stringify(event, null, 2));
  console.log("CONTEXT: \n" + JSON.stringify(context, null, 2));
  const path = event.path;
  const headers = event.multiValueHeaders;
  let redirect;
  if (path === "/aws_mwaa/aws-console-sso") {
    redirect = await login(headers);
  } else {
    redirect = {
      statusCode: 302,
      statusDescription: `Path is not /aws_mwaa/aws-console-sso`,
    };
  }
  console.info(JSON.stringify(redirect));
  return redirect;
};
