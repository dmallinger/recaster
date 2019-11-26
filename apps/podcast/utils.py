import google.cloud.storage
import requests
import uuid

import settings


class PartitionedBlob:
    COMPOSE_LIMIT = 32

    def __init__(self, bucket_name, directory="tmp", respect_compose_limit=True):
        self.bucket_name = bucket_name
        self.directory = directory
        self.respect_compose_limit = respect_compose_limit

        client = google.cloud.storage.Client()
        self.bucket = client.get_bucket(bucket_name)
        self.blobs = []

    def append_blob(self, blob):
        if len(self.blobs) >= self.COMPOSE_LIMIT:
            self.compose(self._make_tmp_blob_name())
        self.blobs.append(blob)
        return blob

    def append_contents(self, contents, **upload_kwargs):
        blob = self._make_blob()
        blob.upload_from_string(contents, **upload_kwargs)
        return self.append_blob(blob)

    def append_file(self, path, **upload_kwargs):
        blob = self._make_blob()
        blob.upload_from_filename(path, **upload_kwargs)
        return self.append_blob(blob)

    def compose(self, path, delete_partitions=True):
        blob = self.bucket.blob(path)
        blob.compose(self.blobs)
        if delete_partitions:
            for _blob in self.blobs:
                _blob.delete()
        self.blobs = [blob]
        return blob

    def _make_blob(self, path=None):
        if path is None:
            path = self._make_tmp_blob_name()
        blob = self.bucket.blob(path)
        return blob

    def _make_tmp_blob_name(self):
        blob_name = uuid.uuid4()
        return f"""{self.directory}/{blob_name}"""


def stream_upload(source_url, destination_path, tmp_path="tmp", bucket_name=None,
                  chunk_size=None):
    if bucket_name is None:
        bucket_name = settings.PODCAST_STORAGE_BUCKET

    if chunk_size is None:
        chunk_size = settings.STREAM_UPLOAD_CHUNK_SIZE

    pblob = PartitionedBlob(bucket_name=bucket_name, directory=tmp_path, respect_compose_limit=True)
    request = requests.get(source_url, stream=True)
    content_type = request.headers["Content-Type"]
    stream = request.iter_content(chunk_size=chunk_size)
    for chunk in stream:
        pblob.append_contents(chunk)
    blob = pblob.compose(destination_path, delete_partitions=True)
    blob.content_type = content_type
    blob.update()
    return blob
