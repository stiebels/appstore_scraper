#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
from multiprocessing import Pool, Manager, cpu_count
from time import sleep
from bs4 import BeautifulSoup
import re


class Scraper(object):
    
    # dummy header
    HEADER = {'user-agent': ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_5)'
                          'AppleWebKit/537.36 (KHTML, like Gecko)'
                          'Chrome/45.0.2454.101 Safari/537.36'),
                          'referer': 'http://google.com/'}
    URL_BASE_ITUNESID = 'http://itunes.apple.com/lookup?id='
    URL_BASE_BUNDLEID = 'http://itunes.apple.com/lookup?bundleId='
    URL_BASE_GOOGLEID = 'https://play.google.com/store/apps/details?id='
    
    NON_DECIMAL = re.compile(r'[^\d.]+')
    
    def __init__(self, ids_raw, pings=2, wait=1, verbose=True, language='default'):
        manager = Manager() # invoking multiprocessing manager
        self.ids_raw = ids_raw
        self.pings = pings # attempts to ping API for one ID until successful retrieval
        self.id_dict = manager.dict() # creating shared dict amongst process instances    
        self.error_dict = manager.dict()
        self._count = manager.Value('i', 0)
        self.wait = wait
        self.verbose = verbose
        self.language = language
        
    
    @property
    def pings(self):
        return self._pings

    @pings.setter
    def pings(self, p):
        if p < 1:
            raise ValueError('minmum 1 ping')
        else:
            self._pings = p
    
    
    def _get_google_descr(self, url):
        page  = requests.get(url, headers=Scraper.HEADER).text
        soup_expatistan = BeautifulSoup(page, "html.parser")
        try:
            descr = soup_expatistan.find("div", itemprop="description").get_text()
            genre = soup_expatistan.find("span", itemprop="genre").get_text()
            rating, ratingCount = [float(entry.replace(',', '')) for entry in soup_expatistan.find("meta", itemprop="ratingValue").get_text().strip(' ').split(" ") if ('.' in entry) or entry.replace(',', '').isdigit()]
            price = float(Scraper.NON_DECIMAL.sub('', soup_expatistan.find("meta", itemprop='price').attrs['content']))
            return [descr, genre, rating, ratingCount, price]
        except(AttributeError) as err:
            self.error_dict[str(url.split('=')[-1])] = str(err)
    

    def _get_json(self, appid):
        
        self._count.value += 1
        
        if self.verbose is True:
            print(str(self._count.value)+' / '+ str(len(self.ids_raw))+' | Errors: '+str(len(self.error_dict))) # prints progress
        
        if self.language=='default':
            lang = ''
        else:
            lang = '&lang='+str(self.language)
        
        if ('google' in str(appid)) or ('android' in str(appid)):
            url = Scraper.URL_BASE_GOOGLEID+str(appid)
        else:
            if appid.isdigit() is True:
                url = Scraper.URL_BASE_ITUNESID+str(appid)+lang
            else:
                url = Scraper.URL_BASE_BUNDLEID+str(appid)+lang


        for ping in range(self.pings): # retry logic
            try:
                # GOOGLE obvious
                if ('google' in str(appid)) or ('android' in str(appid)):
                    descr, genre, rating, ratingCount, price = self._get_google_descr(url)
                    attempt = {'description':str(descr),
                               'primaryGenreName':str(genre),
                               'userRatingCount':ratingCount,
                               'averageUserRating':rating,
                               'price':price}
                    if len(attempt) == 5:
                        self.id_dict[str(appid)] = attempt
                        continue

                raise(TypeError) # Answer invalid; ping Apple
                
            except(TypeError):
                try:
                # APPLE
                    attempt = requests.get(url, headers=Scraper.HEADER).json()
                    if attempt['resultCount'] != 0:
                        self.id_dict[str(appid)] = attempt['results'][0] # dropping resultCount as always 1 in a successful lookup
                        continue
                    
                    raise(KeyError) # Answer invalid; ping Google
                
                except(KeyError, ValueError) as err:
                    try:
                        # GOOGLE
                        descr, genre, rating, ratingCount, price = self._get_google_descr(Scraper.URL_BASE_GOOGLEID+str(appid))
                        attempt = {'description':str(descr),
                               'primaryGenreName':str(genre),
                               'userRatingCount':ratingCount,
                               'averageUserRating':rating,
                               'price':price}
                        if len(attempt)==5:
                            self.id_dict[str(appid)] = attempt
                            continue

                        raise(TypeError) # Answer invalid; store error and next
                        
                    except(ValueError, KeyError, requests.ConnectionError, TypeError) as err:
                        # ERROR
                        self.error_dict[str(appid)] = str(err)
                
                        
    def scrape(self, processes=(cpu_count()-1)): # parallel processes used is (number_of_CPUs - 1)
        with Pool(processes) as pool:
            pool.map(self._get_json, self.ids_raw)
        self.id_dict = dict(self.id_dict) # converting shared objects to pure dicts again
        self.error_dict = dict(self.error_dict)
        return self.id_dict
