#!/bin/bash
pip install --target ./package -r requirements.txt
cd package
zip -r9 ${OLDPWD}/function.zip .
cd $OLDPWD
zip -g function.zip lambda_function.py
