from rest_framework import status
from rest_framework.exceptions import APIException


class OTPNotFoundException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "No active OTP found for this email."
    default_code = "otp_not_found"


class OTPExpiredException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "OTP has expired."
    default_code = "otp_expired"


class OTPExhaustedException(APIException):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    default_detail = "Maximum OTP attempts exceeded. Please request a new code."
    default_code = "otp_max_attempts"


class OTPInvalidException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Invalid OTP."
    default_code = "otp_invalid"
