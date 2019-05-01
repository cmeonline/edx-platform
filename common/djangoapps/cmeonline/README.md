# CME Online: Customizations for User table


Installation
--------
1. Copy this folder into /edx/app/edxapp/edx-platform/common/djangoapps/

2. add the following to lms.env.json
    ```
    "ADDL_INSTALLED_APPS": [
           "cmeonline.association"
        ],
    ```
    ![lms.env.json configuration](docs/lms.env.json-config.png)

3. [DELETE?] Add the following to /edx/app/edxapp/edx-platform/cms/urls.py on or around row 35

4. Run initial database migrations with this command. This is a Django thing to complete the app "registration").
    ```
    sudo -H -u edxapp -s bash
    cd ~
    source /edx/app/edxapp/edxapp_env
    python /edx/app/edxapp/edx-platform/manage.py lms makemigrations association --settings=aw
    ```
    ![django makemigrations initial](docs/django-makemigrations-initial.png)


4. Run full Open edX migrations with this command from the Ubuntu command line as root
    ```
    sudo /home/ubuntu/edx.platform-migrations.sh
    ```
    ![open edx django migrations](docs/platform-migrations-installation.png)


If everything worked successfully then you should find a new field in the User screen of the Django Admin Console:

![django admin user](docs/django-admin-user.png)


Django Admin console
--------
The salesforce integrations are fully maintainable from within the AM Django admin console.
![django admin console](docs/django_admin_screenshot.png)

Staff and/or Super Users can perform CRUD operations on contacts (aka Instructors).
![django admin contacts](docs/django_admin_contact.png)

Staff and/or Super Users can manage salesforce.com connectivity data. Modifications to the salesforce.com configuration parameters take effect immediately. You can test your salesforce.com connection parameters by using the Django command line utility ```python manage.py verifyconnectivity```
![django admin configuration](docs/django_admin_configuration.png)
