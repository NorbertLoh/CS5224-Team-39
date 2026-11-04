"""Private immutable PDF objects, recoverable after a database commit failure."""

from dataclasses import dataclass
from hashlib import sha256
from uuid import UUID

from botocore.exceptions import ClientError

MAX_PDF_BYTES = 10 * 1024 * 1024
PUBLIC_BLOCK = ("BlockPublicAcls", "IgnorePublicAcls", "BlockPublicPolicy", "RestrictPublicBuckets")


@dataclass(frozen=True)
class StoredPDF:
    size_bytes: int
    sha256: str
    patient_id: UUID
    doctor_id: UUID


class PrivatePDFStore:
    def __init__(self, client, bucket):
        self.client, self.bucket = client, bucket

    def verify_private(self):
        block = self.client.get_public_access_block(Bucket=self.bucket)[
            "PublicAccessBlockConfiguration"
        ]
        if not all(block.get(key) is True for key in PUBLIC_BLOCK):
            raise RuntimeError("Document bucket must block all public access")

    def load(self, key, expected):
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
        except ClientError as error:
            if error.response["Error"]["Code"] in {"NoSuchKey", "404", "NotFound"}:
                return None
            raise
        stream = response["Body"]
        try:
            data = stream.read(MAX_PDF_BYTES + 1)
        finally:
            stream.close()
        metadata = response.get("Metadata", {})
        if (
            not data.startswith(b"%PDF-")
            or len(data) > MAX_PDF_BYTES
            or response.get("ContentType") != "application/pdf"
            or response.get("ContentLength") != len(data)
            or metadata.get("sha256") != sha256(data).hexdigest()
            or any(metadata.get(key) != value for key, value in expected.items())
        ):
            raise RuntimeError("Stored document integrity/context check failed")
        return StoredPDF(
            len(data), metadata["sha256"], UUID(metadata["patient-id"]), UUID(metadata["doctor-id"])
        )

    def put(self, key, data, expected, patient_id, doctor_id):
        if not data.startswith(b"%PDF-") or len(data) > MAX_PDF_BYTES:
            raise ValueError("Invalid PDF output")
        digest = sha256(data).hexdigest()
        metadata = {
            **expected,
            "sha256": digest,
            "patient-id": str(patient_id),
            "doctor-id": str(doctor_id),
        }
        try:
            self.client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=data,
                ContentType="application/pdf",
                CacheControl="no-store",
                ServerSideEncryption="AES256",
                Metadata=metadata,
                IfNoneMatch="*",
            )
        except ClientError as error:
            if error.response["Error"]["Code"] not in {"PreconditionFailed", "412"}:
                raise
            existing = self.load(key, expected)
            if existing is None:
                raise RuntimeError("Existing document could not be reconciled") from None
            return existing
        return StoredPDF(len(data), digest, patient_id, doctor_id)
