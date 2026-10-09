import json
import os

import requests
from django.contrib.auth.models import User
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.core.mail import send_mail

from tables.models import Profile, Employee


@api_view(['GET'])
def upload_employee(request):
    # for profile in Profile.objects.all():
    #    if profile.employee.id_filial is None:
    #        url = 'http://localhost:8081/hotels/api/integration/getFilialByUsername?tab=' + str(profile.employee.tabnumber)
    #        response = requests.get(url, verify=False)
    #        response.raise_for_status()
    #        data = json.loads(response.text)
    #        profile.employee.id_filial = data
    #        profile.employee.save()
    #     profile.employee.id_filial =
    url = 'https://edms.sgp.ru/Integration/odata/IEmployees'
    response = requests.get(url, verify=False, auth=(os.environ.get('INTEGRATION_LOGIN'), os.environ.get('INTEGRATION_PASSWORD')))
    try:
        #Employee.objects.all().delete()
        response.raise_for_status()
        data = json.loads(response.text)
        emp_list = []
        user_list = []
        for employee in data['value']:
            if type(employee) is str:
                continue
            name = employee['Name']
            tab_number = employee['Codevecm']
            email = employee['Email']
            if email is None or email == '' or employee['Status'] == 'Closed' or tab_number is None or tab_number == '':
                continue
            username = email.split('@')[0]

            if Employee.objects.filter(tabnumber=tab_number).count() == 0:
                emp = Employee.objects.create(tabnumber=tab_number,
                                                     firstname=name.split(" ")[1],
                                                     lastname=name.split(" ")[0],
                                                     secondname=name.split(" ")[2],
                                                     email=email,
                                                     )
                emp.save()

            if User.objects.filter(username=username).count() == 0:
                user = User.objects.create(username=username, first_name=name.split(" ")[1], last_name=name.split(" ")[0], is_active=True)
                #user_list.append(user)
                user.save()

            emp_list.append(emp)

        #Employee.objects.bulk_create(emp_list)
        #User.objects.bulk_create(user_list)

        profile_list = []
        for user in User.objects.all():
            if Employee.objects.filter(email__contains=user.username).count() == 1:
                employer = Employee.objects.get(email__contains=user.username)
                profile = Profile.objects.create(user=user, employee=employer)
                profile.save()


        return Response({'ok': data})
    except requests.exceptions.RequestException as e:
       return Response({"error": str(e)})
