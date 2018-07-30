REST API Example Usage
======================

This document summarizes some examples of the cloudigrade REST API.

Examples here use the ``http`` command from
`httpie <https://httpie.org/>`_. If you want to follow along with these
exact commands, you may need to ``brew install httpie`` or
``pip install httpie`` first.

These examples also assume you are running cloudigrade on
``localhost:8080`` either via ``docker-compose`` or Django’s built-in
``runserver`` command and that you have correctly configured
cloudigrade’s environment with appropriate variables to allow it to talk
to the various clouds (e.g. ``AWS_ACCESS_KEY_ID``).

Authorization
-------------

As mentioned in `README.md <../README.md>`_, all API calls require an
``Authorization`` header. For convenience, these examples assume you
have an environment variable set like this with an appropriate token
value:

.. code:: bash

    AUTH=Authorization:"Token d1fa223f753e45dd8e311cf84ee2635b0fae5bd8"

Overview
--------

The following resource paths are currently available:

-  ``/api/v1/account/`` returns account data
-  ``/api/v1/report/instances/`` returns daily instance usage data
-  ``/api/v1/report/accounts/`` returns account overview data
-  ``/auth/`` is for authentication

User Account Setup
------------------

This is for accounts with Cloudigrade itself, not telling Cloudigrade
about a user's AWS account.

Create a Cloudigrade account
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Request:

.. code:: bash

    http post localhost:8080/auth/users/create/ \
    username=<username> password=<password>

Response:

::

    HTTP/1.1 201 Created
    Allow: POST, OPTIONS
    Content-Length: 43
    Content-Type: application/json
    Date: Thu, 10 May 2018 20:11:16 GMT
    Server: nginx/1.12.1
    Set-Cookie: 4bf7fdd75eecaf09c9580e6ddbe57ad4=3a0a5f9fe4f5acc709f37456c6867643; path=/; HttpOnly
    Vary: Accept
    X-Frame-Options: SAMEORIGIN

    {
        "email": "",
        "id": <id>,
        "username": "<username>"
    }


Login to Cloudigrade
~~~~~~~~~~~~~~~~~~~~

Request:

.. code:: bash

    http post localhost:8080/auth/token/create/ \
    username=<username> password=<password>

Response:

::

    HTTP/1.1 200 OK
    Allow: POST, OPTIONS
    Content-Length: 57
    Content-Type: application/json
    Date: Thu, 10 May 2018 20:12:16 GMT
    Server: nginx/1.12.1
    Set-Cookie: 4bf7fdd75eecaf09c9580e6ddbe57ad4=3a0a5f9fe4f5acc709f37456c6867643; path=/; HttpOnly
    Vary: Accept
    X-Frame-Options: SAMEORIGIN

    {
        "auth_token": "eb6bedd93ecb158ffdee76f185b90b25ab39a8e9"
    }

The `auth_token` should be used in the `Authorization:` HTTP header.

Log out of Cloudigrade
~~~~~~~~~~~~~~~~~~~~~~

Request:

.. code:: bash

    http localhost:8080/auth/token/destroy/ "${AUTH}"

Response:

::

    HTTP/1.1 204 No Content
    Allow: POST, OPTIONS
    Content-Length: 0
    Date: Thu, 10 May 2018 20:13:32 GMT
    Server: nginx/1.12.1
    Set-Cookie: 4bf7fdd75eecaf09c9580e6ddbe57ad4=3a0a5f9fe4f5acc709f37456c6867643; path=/; HttpOnly
    Vary: Accept
    X-Frame-Options: SAMEORIGIN


Customer Account Setup
----------------------

Create an AWS account
~~~~~~~~~~~~~~~~~~~~~

This request may take a few seconds because of multiple round-trip calls
to the AWS APIs for each region. The "name" attribute is optional and has a
maximum supported length of 256 characters.

Request:

.. code:: bash

    http post localhost:8080/api/v1/account/ "${AUTH}" \
        resourcetype="AwsAccount" \
        account_arn="arn:aws:iam::273470430754:role/role-for-cloudigrade" \
        name="My Favorite Account"

Response:

::

    HTTP/1.1 201 Created
    Allow: GET, POST, HEAD, OPTIONS
    Content-Length: 311
    Content-Type: application/json
    Date: Thu, 05 Jul 2018 16:00:25 GMT
    Location: http://localhost:8080/api/v1/account/3/
    Server: WSGIServer/0.2 CPython/3.6.5
    Vary: Accept
    X-Frame-Options: SAMEORIGIN

    {
        "account_arn": "arn:aws:iam::273470430754:role/role-for-cloudigrade",
        "aws_account_id": "273470430754",
        "created_at": "2018-07-05T16:00:24.473331Z",
        "id": 3,
        "name": "My Favorite Account",
        "resourcetype": "AwsAccount",
        "updated_at": "2018-07-05T16:00:24.473360Z",
        "url": "http://localhost:8080/api/v1/account/3/",
        "user_id": 2
    }

If not specified, the account is created with a ``null`` value for "name".

Request:

.. code:: bash

    http post localhost:8080/api/v1/account/ "${AUTH}" \
        resourcetype="AwsAccount" \
        account_arn="arn:aws:iam::273470430754:role/role-for-cloudigrade"

Response:

::

    HTTP/1.1 201 Created
    Allow: GET, POST, HEAD, OPTIONS
    Content-Length: 294
    Content-Type: application/json
    Date: Thu, 05 Jul 2018 16:01:30 GMT
    Location: http://localhost:8080/api/v1/account/4/
    Server: WSGIServer/0.2 CPython/3.6.5
    Vary: Accept
    X-Frame-Options: SAMEORIGIN

    {
        "account_arn": "arn:aws:iam::273470430754:role/role-for-cloudigrade",
        "aws_account_id": "273470430754",
        "created_at": "2018-07-05T16:01:30.046877Z",
        "id": 4,
        "name": null,
        "resourcetype": "AwsAccount",
        "updated_at": "2018-07-05T16:01:30.046910Z",
        "url": "http://localhost:8080/api/v1/account/4/",
        "user_id": 2
    }

If you attempt to create an AWS account for an ARN that is already in
the system, you should get a 400 error.

Request:

.. code:: bash

    http post localhost:8080/api/v1/account/ "${AUTH}" \
        resourcetype="AwsAccount" \
        account_arn="arn:aws:iam::273470430754:role/role-for-cloudigrade"

Response:

::

    HTTP/1.1 400 Bad Request
    Allow: GET, POST, HEAD, OPTIONS
    Connection: keep-alive
    Content-Length: 69
    Content-Type: application/json
    Date: Mon, 19 Mar 2018 20:28:31 GMT
    Server: nginx/1.13.9
    Vary: Accept
    X-Frame-Options: SAMEORIGIN

    {
        "account_arn": [
            "aws account with this account arn already exists."
        ]
    }


Customer Account Info
---------------------

List all accounts
~~~~~~~~~~~~~~~~~

Request:

.. code:: bash

    http localhost:8080/api/v1/account/ "${AUTH}"

Response:

::

    HTTP/1.1 200 OK
    Allow: GET, POST, HEAD, OPTIONS
    Content-Length: 346
    Content-Type: application/json
    Date: Thu, 05 Jul 2018 16:06:47 GMT
    Server: WSGIServer/0.2 CPython/3.6.5
    Vary: Accept
    X-Frame-Options: SAMEORIGIN

    {
        "count": 1,
        "next": null,
        "previous": null,
        "results": [
            {
                "account_arn": "arn:aws:iam::273470430754:role/role-for-cloudigrade",
                "aws_account_id": "273470430754",
                "created_at": "2018-07-05T16:01:30.046877Z",
                "id": 4,
                "name": null,
                "resourcetype": "AwsAccount",
                "updated_at": "2018-07-05T16:01:30.046910Z",
                "url": "http://localhost:8080/api/v1/account/4/",
                "user_id": 2
            }
        ]
    }

Retrieve a specific account
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Request:

.. code:: bash

    http localhost:8080/api/v1/account/4/ "${AUTH}"

Response:

::

    HTTP/1.1 200 OK
    Allow: GET, PUT, PATCH, HEAD, OPTIONS
    Content-Length: 294
    Content-Type: application/json
    Date: Thu, 05 Jul 2018 16:07:16 GMT
    Server: WSGIServer/0.2 CPython/3.6.5
    Vary: Accept
    X-Frame-Options: SAMEORIGIN

    {
        "account_arn": "arn:aws:iam::273470430754:role/role-for-cloudigrade",
        "aws_account_id": "273470430754",
        "created_at": "2018-07-05T16:01:30.046877Z",
        "id": 4,
        "name": null,
        "resourcetype": "AwsAccount",
        "updated_at": "2018-07-05T16:01:30.046910Z",
        "url": "http://localhost:8080/api/v1/account/4/",
        "user_id": 2
    }

Update a specific account
~~~~~~~~~~~~~~~~~~~~~~~~~

You can update the account object via either HTTP PATCH or HTTP PUT. All
updates require you to specify the "resourcetype".

At the time of this writing, only the "name" property can be changed on the
account object.

Request:

.. code:: bash

    http patch localhost:8080/api/v1/account/4/ "${AUTH}" \
        resourcetype="AwsAccount" \
        name="another name PATCHed in"

Response:

::

    HTTP/1.1 200 OK
    Allow: GET, PUT, PATCH, HEAD, OPTIONS
    Content-Length: 315
    Content-Type: application/json
    Date: Thu, 05 Jul 2018 16:07:47 GMT
    Server: WSGIServer/0.2 CPython/3.6.5
    Vary: Accept
    X-Frame-Options: SAMEORIGIN

    {
        "account_arn": "arn:aws:iam::273470430754:role/role-for-cloudigrade",
        "aws_account_id": "273470430754",
        "created_at": "2018-07-05T16:01:30.046877Z",
        "id": 4,
        "name": "another name PATCHed in",
        "resourcetype": "AwsAccount",
        "updated_at": "2018-07-05T16:07:47.078088Z",
        "url": "http://localhost:8080/api/v1/account/4/",
        "user_id": 2
    }

Because PATCH is intended to replace objects, it must include all potentially
writable fields, which includes "name" and "account_arn".

Request:

.. code:: bash

    http put localhost:8080/api/v1/account/4/ "${AUTH}" \
        resourcetype="AwsAccount" \
        name="this name was PUT in its place" \
        account_arn="arn:aws:iam::273470430754:role/role-for-cloudigrade"

Response:

::

    HTTP/1.1 200 OK
    Allow: GET, PUT, PATCH, HEAD, OPTIONS
    Content-Length: 322
    Content-Type: application/json
    Date: Thu, 05 Jul 2018 16:08:44 GMT
    Server: WSGIServer/0.2 CPython/3.6.5
    Vary: Accept
    X-Frame-Options: SAMEORIGIN

    {
        "account_arn": "arn:aws:iam::273470430754:role/role-for-cloudigrade",
        "aws_account_id": "273470430754",
        "created_at": "2018-07-05T16:01:30.046877Z",
        "id": 4,
        "name": "this name was PUT in its place",
        "resourcetype": "AwsAccount",
        "updated_at": "2018-07-05T16:08:44.004473Z",
        "url": "http://localhost:8080/api/v1/account/4/",
        "user_id": 2
    }

You cannot change the ARN via PUT or PATCH.

Request:

.. code:: bash

    http patch localhost:8080/api/v1/account/4/ "${AUTH}" \
        resourcetype="AwsAccount" \
        account_arn="arn:aws:iam::999999999999:role/role-for-cloudigrade"

Response:

::

    HTTP/1.1 400 Bad Request
    Allow: GET, PUT, PATCH, HEAD, OPTIONS
    Content-Length: 49
    Content-Type: application/json
    Date: Thu, 05 Jul 2018 16:12:12 GMT
    Server: WSGIServer/0.2 CPython/3.6.5
    Vary: Accept
    X-Frame-Options: SAMEORIGIN

    {
        "account_arn": [
            "You cannot change this field."
        ]
    }


Usage Reporting
---------------

Retrieve a daily instance usage report
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

You may include an optional "user_id" query string argument to filter results
down to a specific user if your request is authenticated as a superuser.

You may include an optional "name_pattern" query string argument to filter
results down to activity under accounts whose names match at least one of the
words in that argument.

Request:

.. code:: bash

    http localhost:8080/api/v1/report/instances/ "${AUTH}" \
        start=="2018-03-01T00:00:00" \
        end=="2018-03-04T00:00:00"

Response:

::

    HTTP/1.1 200 OK
    Allow: GET, HEAD, OPTIONS
    Content-Length: 482
    Content-Type: application/json
    Date: Thu, 12 Jul 2018 22:10:35 GMT
    Server: WSGIServer/0.2 CPython/3.6.5
    Vary: Accept
    X-Frame-Options: SAMEORIGIN

    {
        "daily_usage": [
            {
                "date": "2018-03-01T00:00:00Z",
                "openshift_instances": 0,
                "openshift_runtime_seconds": 0.0,
                "rhel_instances": 0,
                "rhel_runtime_seconds": 0.0
            },
            {
                "date": "2018-03-02T00:00:00Z",
                "openshift_instances": 0,
                "openshift_runtime_seconds": 0.0,
                "rhel_instances": 0,
                "rhel_runtime_seconds": 0.0
            },
            {
                "date": "2018-03-03T00:00:00Z",
                "openshift_instances": 0,
                "openshift_runtime_seconds": 0.0,
                "rhel_instances": 0,
                "rhel_runtime_seconds": 0.0
            }
        ],
        "instances_seen_with_openshift": 0,
        "instances_seen_with_rhel": 0
    }


Retrieve an account overview
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Request:

.. code:: bash

    http localhost:8080/api/v1/report/accounts/ "${AUTH}" \
        start=="2018-03-01T00:00:00" \
        end=="2018-04-01T00:00:00"

Response:

::

    HTTP/1.1 200 OK
    Allow: GET, HEAD, OPTIONS
    Content-Length: 483
    Content-Type: application/json
    Date: Fri, 06 Jul 2018 18:32:16 GMT
    Server: WSGIServer/0.2 CPython/3.6.4
    Vary: Accept
    X-Frame-Options: SAMEORIGIN

    {
        "cloud_account_overviews": [
            {
                "arn": "arn:aws:iam::114204391493:role/role-for-cloudigrade",
                "cloud_account_id": "114204391493",
                "creation_date": "2018-07-06T15:09:21.442412Z",
                "id": 1,
                "images": null,
                "instances": null,
                "name": "account-for-aiken",
                "openshift_instances": null,
                "rhel_instances": null,
                "type": "aws",
                "user_id": 1
            },
            ...
        ]
    }

If you attempt to retrieve cloud account overviews without specifying a
start and end date, you should get a 400 error.

Request:

.. code:: bash

    http localhost:8080/api/v1/report/accounts/ "${AUTH}"

Response:

::

    HTTP/1.1 400 Bad Request
    Allow: GET, HEAD, OPTIONS
    Content-Length: 71
    Content-Type: application/json
    Date: Fri, 06 Jul 2018 18:37:58 GMT
    Server: WSGIServer/0.2 CPython/3.6.4
    Vary: Accept
    X-Frame-Options: SAMEORIGIN

    {
        "end": [
            "This field is required."
        ],
        "start": [
            "This field is required."
        ]
    }

You may include an optional "name_pattern" query string argument to filter
results down to activity under accounts whose names match at least one of the
words in that argument.

You may include an optional "account_id" query string argument to filter
results down to activity for a specific clount (Cloud Account). This can be
combined with the "user_id" argument if the caller is a superuser to get
information specific to a different user.

In this example, an account named "greatest account ever" is included because
it contains the word "eat" even though it does not contain the word "tofu".

Request:

.. code:: bash

    http localhost:8080/api/v1/report/accounts/ "${AUTH}" \
        start=="2018-01-10T00:00:00" \
        end=="2018-01-15T00:00:00" \
        name_pattern=="eat tofu"

Response:

::

    HTTP/1.1 200 OK
    Allow: GET, HEAD, OPTIONS
    Content-Length: 266
    Content-Type: application/json
    Date: Thu, 19 Jul 2018 21:13:57 GMT
    Server: WSGIServer/0.2 CPython/3.6.5
    Vary: Accept
    X-Frame-Options: SAMEORIGIN

    {
        "cloud_account_overviews": [
            {
                "arn": "arn:aws:iam::058091732613:role/Marcus Colon",
                "cloud_account_id": "058091732613",
                "creation_date": "2018-01-01T00:00:00Z",
                "id": 5,
                "images": 3,
                "instances": 4,
                "name": "greatest account ever",
                "openshift_instances": 0,
                "rhel_instances": 2,
                "type": "aws",
                "user_id": 1
            }
        ]
    }


User Info
---------------------

List all users
~~~~~~~~~~~~~~~~~

Request:

.. code:: bash

    http localhost:8080/api/v1/user/ "${AUTH}"

Response:

::

    HTTP/1.1 200 OK
    Allow: GET, HEAD
    Content-Length: 346
    Content-Type: application/json
    Date: Thu, 19 Jul 2018 16:06:47 GMT
    Server: WSGIServer/0.2 CPython/3.6.5
    Vary: Accept
    X-Frame-Options: SAMEORIGIN

    [
        {
            "id": 1,
            "username": "user1",
            "is_superuser": true
        },
        {
            "id": 34,
            "username": "customer1",
            "is_superuser": false
        }
    ]

Retrieve a specific user
~~~~~~~~~~~~~~~~~~~~~~~~

Request:

.. code:: bash

    http localhost:8080/api/v1/user/1/ "${AUTH}"

Response:

::

    HTTP/1.1 200 OK
    Allow: GET, HEAD
    Content-Length: 294
    Content-Type: application/json
    Date: Thu, 19 Jul 2018 16:07:16 GMT
    Server: WSGIServer/0.2 CPython/3.6.5
    Vary: Accept
    X-Frame-Options: SAMEORIGIN

    {
        "id": 1,
        "username": "user1",
        "is_superuser": true
    }


Machine Images
--------------
Listing Images
~~~~~~~~~~~~~~

Below command will return all images belonging to the user that makes the request.

Request:

.. code:: bash

    http get http://cloudigrade.127.0.0.1.nip.io/api/v1/image/ Authorization:"Token ${USER_TOKEN}"

Response:

::

    HTTP/1.1 200 OK
    Allow: GET, HEAD, OPTIONS
    Cache-control: private
    Content-Length: 1610
    Content-Type: application/json
    Date: Mon, 30 Jul 2018 15:20:26 GMT
    Server: nginx/1.12.1
    Set-Cookie: 7ff040c48489ca1dd99b0528a4d40fe5=7ce0ca28d38f4fd407c4e0bdb29358ae; path=/; HttpOnly
    Vary: Accept
    X-Frame-Options: SAMEORIGIN

    {
        "count": 4,
        "next": null,
        "previous": null,
        "results": [
            {
                "account": "http://cloudigrade.127.0.0.1.nip.io/api/v1/account/1/",
                "created_at": "2018-07-30T15:41:16.310031Z",
                "ec2_ami_id": "ami-plain",
                "id": 1,
                "is_encrypted": false,
                "openshift": false,
                "openshift_challenged": false,
                "openshift_detected": false,
                "resourcetype": "AwsMachineImage",
                "rhel": false,
                "rhel_challenged": false,
                "rhel_detected": false,
                "status": "pending",
                "updated_at": "2018-07-30T15:15:11.214092Z"
            },
            {
                "account": "http://cloudigrade.127.0.0.1.nip.io/api/v1/account/1/",
                "created_at": "2018-07-30T15:41:16.317326Z",
                "ec2_ami_id": "ami-rhel7",
                "id": 2,
                "is_encrypted": false,
                "openshift": true,
                "openshift_challenged": true,
                "openshift_detected": false,
                "resourcetype": "AwsMachineImage",
                "rhel": false,
                "rhel_challenged": true,
                "rhel_detected": true,
                "status": "pending",
                "updated_at": "2018-07-30T15:14:19.829340Z"
            },
            {
                "account": "http://cloudigrade.127.0.0.1.nip.io/api/v1/account/1/",
                "created_at": "2018-07-30T15:41:16.330278Z",
                "ec2_ami_id": "ami-openshift",
                "id": 3,
                "is_encrypted": false,
                "openshift": false,
                "openshift_challenged": true,
                "openshift_detected": true,
                "resourcetype": "AwsMachineImage",
                "rhel": true,
                "rhel_challenged": true,
                "rhel_detected": false,
                "status": "pending",
                "updated_at": "2018-07-30T15:14:06.164469Z"
            },
            {
                "account": "http://cloudigrade.127.0.0.1.nip.io/api/v1/account/1/",
                "created_at": "2018-07-30T15:41:16.343734Z",
                "ec2_ami_id": "ami-both",
                "id": 4,
                "is_encrypted": false,
                "openshift": true,
                "openshift_challenged": false,
                "openshift_detected": true,
                "resourcetype": "AwsMachineImage",
                "rhel": true,
                "rhel_challenged": false,
                "rhel_detected": true,
                "status": "pending",
                "updated_at": "2018-07-30T15:41:16.355784Z"
            }
        ]
    }

A superuser will see all images belonging to all accounts.

Request:

.. code:: bash

    http get http://cloudigrade.127.0.0.1.nip.io/api/v1/image/ Authorization:"Token ${SUPER_TOKEN}"

Response:

::

    HTTP/1.1 200 OK
    Allow: GET, HEAD, OPTIONS
    Cache-control: private
    Content-Length: 2005
    Content-Type: application/json
    Date: Mon, 30 Jul 2018 15:23:25 GMT
    Server: nginx/1.12.1
    Set-Cookie: 7ff040c48489ca1dd99b0528a4d40fe5=7ce0ca28d38f4fd407c4e0bdb29358ae; path=/; HttpOnly
    Vary: Accept
    X-Frame-Options: SAMEORIGIN

    {
        "count": 5,
        "next": null,
        "previous": null,
        "results": [
            {
                "account": "http://cloudigrade.127.0.0.1.nip.io/api/v1/account/1/",
                "created_at": "2018-07-30T15:41:16.310031Z",
                "ec2_ami_id": "ami-plain",
                "id": 1,
                "is_encrypted": false,
                "openshift": false,
                "openshift_challenged": false,
                "openshift_detected": false,
                "resourcetype": "AwsMachineImage",
                "rhel": false,
                "rhel_challenged": false,
                "rhel_detected": false,
                "status": "pending",
                "updated_at": "2018-07-30T15:15:11.214092Z"
            },
            {
                "account": "http://cloudigrade.127.0.0.1.nip.io/api/v1/account/1/",
                "created_at": "2018-07-30T15:41:16.317326Z",
                "ec2_ami_id": "ami-rhel7",
                "id": 2,
                "is_encrypted": false,
                "openshift": true,
                "openshift_challenged": true,
                "openshift_detected": false,
                "resourcetype": "AwsMachineImage",
                "rhel": false,
                "rhel_challenged": true,
                "rhel_detected": true,
                "status": "pending",
                "updated_at": "2018-07-30T15:14:19.829340Z"
            },
            {
                "account": "http://cloudigrade.127.0.0.1.nip.io/api/v1/account/1/",
                "created_at": "2018-07-30T15:41:16.330278Z",
                "ec2_ami_id": "ami-openshift",
                "id": 3,
                "is_encrypted": false,
                "openshift": false,
                "openshift_challenged": true,
                "openshift_detected": true,
                "resourcetype": "AwsMachineImage",
                "rhel": true,
                "rhel_challenged": true,
                "rhel_detected": false,
                "status": "pending",
                "updated_at": "2018-07-30T15:14:06.164469Z"
            },
            {
                "account": "http://cloudigrade.127.0.0.1.nip.io/api/v1/account/1/",
                "created_at": "2018-07-30T15:41:16.343734Z",
                "ec2_ami_id": "ami-both",
                "id": 4,
                "is_encrypted": false,
                "openshift": true,
                "openshift_challenged": false,
                "openshift_detected": true,
                "resourcetype": "AwsMachineImage",
                "rhel": true,
                "rhel_challenged": false,
                "rhel_detected": true,
                "status": "pending",
                "updated_at": "2018-07-30T15:41:16.355784Z"
            },
            {
                "account": "http://cloudigrade.127.0.0.1.nip.io/api/v1/account/2/",
                "created_at": "2018-07-30T15:41:16.362110Z",
                "ec2_ami_id": "ami-rhel_other",
                "id": 5,
                "is_encrypted": false,
                "openshift": false,
                "openshift_challenged": false,
                "openshift_detected": false,
                "resourcetype": "AwsMachineImage",
                "rhel": true,
                "rhel_challenged": false,
                "rhel_detected": true,
                "status": "pending",
                "updated_at": "2018-07-30T15:41:16.367853Z"
            }
        ]
    }

A superuser can also filter the images down to a specific user by using the optional
``user_id`` query string argument.

Request:

.. code:: bash

    http get http://cloudigrade.127.0.0.1.nip.io/api/v1/image/ user_id==2 Authorization:"Token ${SUPER_TOKEN}"

Response:

::

    HTTP/1.1 200 OK
    Allow: GET, HEAD, OPTIONS
    Cache-control: private
    Content-Length: 446
    Content-Type: application/json
    Date: Mon, 30 Jul 2018 15:26:30 GMT
    Server: nginx/1.12.1
    Set-Cookie: 7ff040c48489ca1dd99b0528a4d40fe5=7ce0ca28d38f4fd407c4e0bdb29358ae; path=/; HttpOnly
    Vary: Accept
    X-Frame-Options: SAMEORIGIN

    {
        "count": 1,
        "next": null,
        "previous": null,
        "results": [
            {
                "account": "http://cloudigrade.127.0.0.1.nip.io/api/v1/account/2/",
                "created_at": "2018-07-30T15:41:16.362110Z",
                "ec2_ami_id": "ami-rhel_other",
                "id": 5,
                "is_encrypted": false,
                "openshift": false,
                "openshift_challenged": false,
                "openshift_detected": false,
                "resourcetype": "AwsMachineImage",
                "rhel": true,
                "rhel_challenged": false,
                "rhel_detected": true,
                "status": "pending",
                "updated_at": "2018-07-30T15:41:16.367853Z"
            }
        ]
    }

Listing a Specific Image
~~~~~~~~~~~~~~~~~~~~~~~~

Request:

.. code:: bash

    http get http://cloudigrade.127.0.0.1.nip.io/api/v1/image/1/ Authorization:"Token ${USER_TOKEN}"

Response:

::

    HTTP/1.1 200 OK
    Allow: GET, PUT, PATCH, HEAD, OPTIONS
    Cache-control: private
    Content-Length: 391
    Content-Type: application/json
    Date: Mon, 30 Jul 2018 15:29:04 GMT
    Server: nginx/1.12.1
    Set-Cookie: 7ff040c48489ca1dd99b0528a4d40fe5=7ce0ca28d38f4fd407c4e0bdb29358ae; path=/; HttpOnly
    Vary: Accept
    X-Frame-Options: SAMEORIGIN

    {
        "account": "http://cloudigrade.127.0.0.1.nip.io/api/v1/account/1/",
        "created_at": "2018-07-30T15:41:16.310031Z",
        "ec2_ami_id": "ami-plain",
        "id": 1,
        "is_encrypted": false,
        "openshift": false,
        "openshift_challenged": false,
        "openshift_detected": false,
        "resourcetype": "AwsMachineImage",
        "rhel": false,
        "rhel_challenged": false,
        "rhel_detected": false,
        "status": "pending",
        "updated_at": "2018-07-30T15:15:11.214092Z"
    }

Same, as a superuser.

Request:

.. code:: bash

    http get http://cloudigrade.127.0.0.1.nip.io/api/v1/image/1/ Authorization:"Token ${SUPER_TOKEN}"

Response:

::

    HTTP/1.1 200 OK
    Allow: GET, PUT, PATCH, HEAD, OPTIONS
    Cache-control: private
    Content-Length: 391
    Content-Type: application/json
    Date: Mon, 30 Jul 2018 15:28:16 GMT
    Server: nginx/1.12.1
    Set-Cookie: 7ff040c48489ca1dd99b0528a4d40fe5=7ce0ca28d38f4fd407c4e0bdb29358ae; path=/; HttpOnly
    Vary: Accept
    X-Frame-Options: SAMEORIGIN

    {
        "account": "http://cloudigrade.127.0.0.1.nip.io/api/v1/account/1/",
        "created_at": "2018-07-30T15:41:16.310031Z",
        "ec2_ami_id": "ami-plain",
        "id": 1,
        "is_encrypted": false,
        "openshift": false,
        "openshift_challenged": false,
        "openshift_detected": false,
        "resourcetype": "AwsMachineImage",
        "rhel": false,
        "rhel_challenged": false,
        "rhel_detected": false,
        "status": "pending",
        "updated_at": "2018-07-30T15:15:11.214092Z"
    }

Issuing Challenges
~~~~~~~~~~~~~~~~~~
Note that ``resourcetype`` is required when making these calls.

Request:

.. code:: bash

    http patch http://cloudigrade.127.0.0.1.nip.io/api/v1/image/1/ \
        resourcetype=AwsMachineImage \
        rhel_challenged=True \
        Authorization:"Token ${USER_TOKEN}"

Response:

::

    HTTP/1.1 200 OK
    Allow: GET, PUT, PATCH, HEAD, OPTIONS
    Content-Length: 389
    Content-Type: application/json
    Date: Mon, 30 Jul 2018 15:31:02 GMT
    Server: nginx/1.12.1
    Set-Cookie: 7ff040c48489ca1dd99b0528a4d40fe5=7ce0ca28d38f4fd407c4e0bdb29358ae; path=/; HttpOnly
    Vary: Accept
    X-Frame-Options: SAMEORIGIN

    {
        "account": "http://cloudigrade.127.0.0.1.nip.io/api/v1/account/1/",
        "created_at": "2018-07-30T15:41:16.310031Z",
        "ec2_ami_id": "ami-plain",
        "id": 1,
        "is_encrypted": false,
        "openshift": false,
        "openshift_challenged": false,
        "openshift_detected": false,
        "resourcetype": "AwsMachineImage",
        "rhel": true,
        "rhel_challenged": true,
        "rhel_detected": false,
        "status": "pending",
        "updated_at": "2018-07-30T15:31:02.026393Z"
    }

If you'd like to remove a challenge, simply send the same challenge with False as the value.

Request:

.. code:: bash

    http patch http://cloudigrade.127.0.0.1.nip.io/api/v1/image/1/ \
        resourcetype=AwsMachineImage \
        rhel_challenged=False \
        Authorization:"Token ${USER_TOKEN}"

Response:

::

    HTTP/1.1 200 OK
    Allow: GET, PUT, PATCH, HEAD, OPTIONS
    Content-Length: 389
    Content-Type: application/json
    Date: Mon, 30 Jul 2018 15:31:02 GMT
    Server: nginx/1.12.1
    Set-Cookie: 7ff040c48489ca1dd99b0528a4d40fe5=7ce0ca28d38f4fd407c4e0bdb29358ae; path=/; HttpOnly
    Vary: Accept
    X-Frame-Options: SAMEORIGIN

    {
        "account": "http://cloudigrade.127.0.0.1.nip.io/api/v1/account/1/",
        "created_at": "2018-07-30T15:41:16.310031Z",
        "ec2_ami_id": "ami-plain",
        "id": 1,
        "is_encrypted": false,
        "openshift": false,
        "openshift_challenged": false,
        "openshift_detected": false,
        "resourcetype": "AwsMachineImage",
        "rhel": false,
        "rhel_challenged": false,
        "rhel_detected": false,
        "status": "pending",
        "updated_at": "2018-07-30T15:31:02.026393Z"
    }

You can challenge both at the same time.

Request:

.. code:: bash

    http patch http://cloudigrade.127.0.0.1.nip.io/api/v1/image/1/ \
        resourcetype=AwsMachineImage \
        rhel_challenged=True \
        openshift_challenged=True \
        Authorization:"Token ${USER_TOKEN}"

Response:

::

    HTTP/1.1 200 OK
    Allow: GET, PUT, PATCH, HEAD, OPTIONS
    Content-Length: 389
    Content-Type: application/json
    Date: Mon, 30 Jul 2018 15:31:02 GMT
    Server: nginx/1.12.1
    Set-Cookie: 7ff040c48489ca1dd99b0528a4d40fe5=7ce0ca28d38f4fd407c4e0bdb29358ae; path=/; HttpOnly
    Vary: Accept
    X-Frame-Options: SAMEORIGIN

    {
        "account": "http://cloudigrade.127.0.0.1.nip.io/api/v1/account/1/",
        "created_at": "2018-07-30T15:41:16.310031Z",
        "ec2_ami_id": "ami-plain",
        "id": 1,
        "is_encrypted": false,
        "openshift": true,
        "openshift_challenged": true,
        "openshift_detected": false,
        "resourcetype": "AwsMachineImage",
        "rhel": true,
        "rhel_challenged": true,
        "rhel_detected": false,
        "status": "pending",
        "updated_at": "2018-07-30T15:31:02.026393Z"
    }

Miscellaneous Commands
----------------------

Retrieve current cloud account ids used by the application
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Request:

.. code:: bash

    http localhost:8080/api/v1/sysconfig/ "${AUTH}"

Response:

::

    HTTP/1.1 200 OK
    Allow: GET, HEAD, OPTIONS
    Content-Length: 33
    Content-Type: application/json
    Date: Mon, 25 Jun 2018 17:22:50 GMT
    Server: WSGIServer/0.2 CPython/3.6.5
    Vary: Accept
    X-Frame-Options: SAMEORIGIN

    {
        "aws_account_id": "123456789012"
    }

If you attempt to retrieve account ids without authentication you'll receive a 401 error.
