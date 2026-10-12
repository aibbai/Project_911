<img src=https://notion-emojis.s3-us-west-2.amazonaws.com/prod/svg-twitter/1f691.svg width="50">  

# 응급의료 대응 최적화 프로젝트
> 서울시 자치구의 구급통계·생활인구·응급의료시설 데이터를 활용해, 자치구별 구급 수요를 분석하고 미래 수요 예측과 실시간 응급실 정보를 연계하는 AI 프로젝트 


## 📑 목차
[배경 및 문제 정의](https://github.com/aibbai/Project_911#-%EB%B0%B0%EA%B2%BD-%EB%B0%8F-%EB%AC%B8%EC%A0%9C-%EC%A0%95%EC%9D%98)<br>
[프로젝트 목표](https://github.com/aibbai/Project_911#-%ED%94%84%EB%A1%9C%EC%A0%9D%ED%8A%B8-%EB%AA%A9%ED%91%9C)<br>
[프로젝트 소개](https://github.com/aibbai/Project_911#-%ED%94%84%EB%A1%9C%EC%A0%9D%ED%8A%B8-%EC%86%8C%EA%B0%9C)<br>
[데이터 수집 및 분석](https://github.com/aibbai/Project_911#%EB%8D%B0%EC%9D%B4%ED%84%B0-%EC%88%98%EC%A7%91-%EB%B0%8F-%EB%B6%84%EC%84%9D)<br>
[모델 개발 및 성능 평가](https://github.com/aibbai/Project_911#-%EB%AA%A8%EB%8D%B8-%EA%B0%9C%EB%B0%9C-%EB%B0%8F-%EC%84%B1%EB%8A%A5-%ED%8F%89%EA%B0%80)<br>
[웹 서비스 구현](https://github.com/aibbai/Project_911#-%EC%9B%B9-%EC%84%9C%EB%B9%84%EC%8A%A4-%EA%B5%AC%ED%98%84)<br>
[프로젝트 결론](https://github.com/aibbai/Project_911#-%ED%94%84%EB%A1%9C%EC%A0%9D%ED%8A%B8-%EA%B2%B0%EB%A1%A0)<br>
[활용 데이터](https://github.com/aibbai/Project_911#-%ED%99%9C%EC%9A%A9-%EB%8D%B0%EC%9D%B4%ED%84%B0)<br>

## 🎯 배경 및 문제 정의

### 프로젝트 배경

- 구급 활동은 지역·시기·생활인구 등에 따라 발생 패턴이 달라질 수 있음
- 생활인구와 구급 수요의 관계를 분석하면 지역별 특성을 파악할 수 있음
- 미래 구급 수요를 예측하면 지역별 응급의료 대응을 지원할 수 있음
- 실제 응급상황에서는 구급 수요뿐 아니라 현재 이용 가능한 응급실·병상 정보도 중요함

### 핵심 질문

- 어떤 자치구에서 구급 수요가 높은가?
- 생활인구와 구급 수요에는 어떤 관계가 있는가?
- 미래 구급 수요를 예측할 수 있는가?
- 예측 수요와 응급의료 자원 현황을 함께 확인할 수 있는가?

## 🎯 프로젝트 목표

1. **자치구별 구급 수요 분석**
    - 출동건수·이송건수·이송환자수 비교
    - 환자유형 및 월별·계절별 패턴 분석
2. **생활인구와 구급 수요 관계 분석**
    - 주간·야간 생활인구와 구급 수요 비교
    - 생활인구 규모 대비 구급 수요 분석
3. **구급 수요 예측**
    - 과거 구급활동 데이터를 기반으로 미래 출동 또는 이송 수요 예측
    - 실제값과 예측값 비교 및 모델 평가
4. **응급의료시설 연계**
    - 응급의료기관 위치·시설 정보 확인
    - 실시간 응급실 가용병상 정보 연계
5. **웹 서비스 구현**
    - 지역 분석·수요 예측·응급의료시설·병상 현황 통합 제공

## 📌 프로젝트 소개
<img width="960" height="540" alt="Image"
src="https://raw.githubusercontent.com/aibbai/Project_911/master/Jiyoon/ppt이미지/슬라이드2.JPG">
<img width="960" height="540" alt="Image"
src="https://raw.githubusercontent.com/aibbai/Project_911/master/Jiyoon/ppt이미지/슬라이드4.JPG"><img width="960" height="540" alt="Image"
src="https://raw.githubusercontent.com/aibbai/Project_911/master/Jiyoon/ppt이미지/슬라이드5.JPG"><img width="960" height="540" alt="Image"
src="https://raw.githubusercontent.com/aibbai/Project_911/master/Jiyoon/ppt이미지/슬라이드7.JPG">


## 📝데이터 수집 및 분석

<img width="960" height="540" alt="Image"
src="https://raw.githubusercontent.com/aibbai/Project_911/master/Jiyoon/ppt이미지/슬라이드9.JPG">
<img width="960" height="540" alt="Image"
src="https://raw.githubusercontent.com/aibbai/Project_911/master/Jiyoon/ppt이미지/슬라이드13.JPG">
<img width="960" height="540" alt="Image"
src="https://raw.githubusercontent.com/aibbai/Project_911/master/Jiyoon/ppt이미지/슬라이드16.JPG">
<img width="960" height="540" alt="Image"
src="https://raw.githubusercontent.com/aibbai/Project_911/master/Jiyoon/ppt이미지/슬라이드18.JPG">

## 🔍 모델 개발 및 성능 평가

<img width="960" height="540" alt="Image"
src="https://raw.githubusercontent.com/aibbai/Project_911/master/Jiyoon/ppt이미지/슬라이드23.JPG">
<img width="960" height="540" alt="Image"
src="https://raw.githubusercontent.com/aibbai/Project_911/master/Jiyoon/ppt이미지/슬라이드26.JPG">
<img width="960" height="540" alt="Image"
src="https://raw.githubusercontent.com/aibbai/Project_911/master/Jiyoon/ppt이미지/슬라이드27.JPG">
<img width="960" height="540" alt="Image"
src="https://raw.githubusercontent.com/aibbai/Project_911/master/Jiyoon/ppt이미지/슬라이드28.JPG">
<img width="960" height="540" alt="Image"
src="https://raw.githubusercontent.com/aibbai/Project_911/master/Jiyoon/ppt이미지/슬라이드30.JPG">
<img width="960" height="540" alt="Image"
src="https://raw.githubusercontent.com/aibbai/Project_911/master/Jiyoon/ppt이미지/슬라이드32.JPG">
<img width="960" height="540" alt="Image"
src="https://raw.githubusercontent.com/aibbai/Project_911/master/Jiyoon/ppt이미지/슬라이드33.JPG">

## 💻 웹 서비스 구현 

<img width="960" height="540" alt="Image"
src="https://raw.githubusercontent.com/aibbai/Project_911/master/Jiyoon/ppt이미지/슬라이드36.JPG">
<img width="960" height="540" alt="Image"
src="https://raw.githubusercontent.com/aibbai/Project_911/master/Jiyoon/ppt이미지/슬라이드38.JPG">
<img width="960" height="540" alt="Image"
src="https://raw.githubusercontent.com/aibbai/Project_911/master/Jiyoon/ppt이미지/슬라이드39.JPG">
<img width="960" height="540" alt="Image"
src="https://raw.githubusercontent.com/aibbai/Project_911/master/Jiyoon/ppt이미지/슬라이드40.JPG">
<img width="960" height="540" alt="Image"
src="https://raw.githubusercontent.com/aibbai/Project_911/master/Jiyoon/ppt이미지/슬라이드41.JPG">

## 🚨 프로젝트 결론

<img width="960" height="540" alt="Image"
src="https://raw.githubusercontent.com/aibbai/Project_911/master/Jiyoon/ppt이미지/슬라이드42.JPG">

## 📚 활용 데이터

  - 소방청 구급통계 서비스 API
  - 서울시 소방 구급 출동 현황
  - 서울시 119 구급활동 실적
  - 자치구단위 서울생활인구
  - 응급의료기관 정보 조회 API
  - 전국 응급의료기관 표준데이터

##

- **프로젝트 기간**: 2026.09.28 ~ 2025.10.11 (2주)
- **주요 기술**:  
   <div>
     <img src="https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white">
     <img src="https://img.shields.io/badge/Pandas-150458?style=for-the-badge&logo=pandas&logoColor=white">
     <img src="https://img.shields.io/badge/NumPy-013243?style=for-the-badge&logo=numpy&logoColor=white">
     <img src="https://img.shields.io/badge/Matplotlib-11557c?style=for-the-badge&logo=python&logoColor=white">
     <img src="https://img.shields.io/badge/Seaborn-3776AB?style=for-the-badge&logo=python&logoColor=white">
   </div>
   <div>
     <img src="https://img.shields.io/badge/TensorFlow-FF6F00?style=for-the-badge&logo=tensorflow&logoColor=white">
     <img src="https://img.shields.io/badge/scikit--learn-F7931E?style=for-the-badge&logo=scikit-learn&logoColor=white">
     <img src="https://img.shields.io/badge/LightGBM-02569B?style=for-the-badge&logoColor=white">
     <img src="https://img.shields.io/badge/CatBoost-FFCC00?style=for-the-badge&logoColor=black">
     <img src="https://img.shields.io/badge/XGBoost-EB5424?style=for-the-badge&logoColor=white">
   </div>
   <div>
     <img src="https://img.shields.io/badge/Flask-000000?style=for-the-badge&logo=flask&logoColor=white">
     <img src="https://img.shields.io/badge/Bootstrap-7952B3?style=for-the-badge&logo=bootstrap&logoColor=white">
     <img src="https://img.shields.io/badge/HTML5-E34F26?style=for-the-badge&logo=html5&logoColor=white">
     <img src="https://img.shields.io/badge/CSS3-1572B6?style=for-the-badge&logo=css3&logoColor=white">
     <img src="https://img.shields.io/badge/JavaScript-F7DF1E?style=for-the-badge&logo=javascript&logoColor=black">
   </div>
