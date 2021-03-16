/*
"""
Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the "Software"), to deal in
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
the Software, and to permit persons to whom the Software is furnished to do so.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
"""
*/

// dependencies
const AWS = require('aws-sdk');
const util = require('util');
const resizeImg = require('resize-img');


// constants
const MAX_WIDTH = process.env.MAX_WIDTH ? process.env.MAX_WIDTH : 250;
const MAX_HEIGHT = process.env.MAX_HEIGHT ? process.env.MAX_HEIGHT : 250;


// get reference to S3 client
const s3 = new AWS.S3();

exports.handler = async (event, context, callback) => {
    console.log("Reading input from event:\n", event);
    let response;
    // get the object from S3 first
    const s3Bucket = event.s3Bucket;
    const thumbnailBucket = s3Bucket;
    try {
        // Object key may have spaces or unicode non-ASCII characters.
        const srcKey = decodeURIComponent(event.s3Key.replace(/\+/g, " "));
        const s3Data = await s3.getObject({
            Bucket: s3Bucket,
            Key: srcKey
        }).promise();
        let resizeOptions = {
            width: parseInt(MAX_WIDTH),
            height: parseInt(MAX_HEIGHT)
        }
        console.log(resizeOptions);

        const image = await resizeImg(s3Data.Body, resizeOptions);
        console.log("resized the image");

        const destKey = "resized-" + srcKey;

        const s3PutParams = {
            Bucket: thumbnailBucket,
            Key: destKey
            // ContentType: "image/" + identified.format.toLowerCase()
        };
        s3PutParams.Body = image;
        response = {thumbnail:{
            Bucket: thumbnailBucket,
            Key: destKey
        }};
        await s3.upload(s3PutParams).promise();
    } catch (error) {
        console.log(error)
    }
    return response;
    // upload the result image back to s3

}
