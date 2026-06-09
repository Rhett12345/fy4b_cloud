MODULE AGRI_cloud_type_II

!C-----------------------------------------------------------------------
!c !F90
!C
!C Description:
!C     It is a primary program for analyzing cloud types  
!c     USE Himawari08 ch14[11.2],and cloud top height,loud top temperature,
!C     cloud phase,loud optical thickness,loud particle effective radius
!c
!c Input PARAMETERs
!c     micaro and macro characteristic properties of every cloud type (in program)
!C
!c Output
!c     cloud type of disk(cloud types:CI,AS/AC,Cu,As,Ac,Ns,Cb,and multi-layer CI/AS/AC,CI/SC/ST,AS/AC/SC/ST)
!C
!c !Author's information
!C  Author: Wu Xiao
!c  E-mail: wuxiao@cma.gov.cn
!c  Tel   : 86-010-68407237
!c  National Satellite Meteorological Center
!C
!c !END
!C-----------------------------------------------------------------------

! USE Module
USE data_arrays_module
USE out_arrays_module
USE names_module
USE numerical_module
!USE planck_module
USE constant_module
USE pixel_common_module

IMPLICIT NONE
!+++++++++++++++++++ step 1: define variables ++++++++++++++++++++++++++

!-----------------------------------------------------------------------
! declare public routines
!-----------------------------------------------------------------------
PUBLIC :: AGRI_cloudtype_II

!-----------------------------------------------------------------------
! declare private routines
!-----------------------------------------------------------------------
PRIVATE ::  AGRI_change, &
			AGRI_cloudtype_analysis
!--- include PARAMETERs

 Real(kind=real4), parameter, private:: zen_max = 70.0
 Real(kind=real4), parameter, private:: solzen_max = 65.0

!+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++	
		
CONTAINS
!+++++++++++++++++++ step 2: SUBROUTINEs + +++++++++++++++++++++++++++++
!~~~~~~~~~~~~~~~~~~~ SUBROUTINE 1: TYPE_main ~~~~~~~~~~~~~~~~~~~~~~~~~~~~
SUBROUTINE AGRI_cloudtype_II

!~~~~~~~~~~~~~~~~~~~ SUBROUTINE 2: TYPE_sub ~~~~~~~~~~~~~~~~~~~~~~~~~~~~
!SUBROUTINE AGRI_change
!~~~~~~~~~~~~~~~~~~~ SUBROUTINE 3: TYPE_sub ~~~~~~~~~~~~~~~~~~~~~~~~~~~~
!SUBROUTINE AGRI_cloudtypeanalysis

! 1. define variables
INTEGER(KIND=int4) :: ielem
INTEGER(KIND=int4) :: iline
REAL(KIND=real4) :: cloudtopHei !cloudtop geopotential height(M)
REAL(KIND=real4) :: cloudtopTem !cloudtop temperature(K)
REAL(KIND=real4) :: cloudRad    !effective radius of cloud 
INTEGER(KIND=int1) :: cloudPhase   !cloud phase
REAL(KIND=real4) :: cloudOpti   !cloud optical thickness
REAL(KIND=real4) :: bt14          !brightness temperature of channel 14 of Himawari08(K)
REAL(KIND=real4) :: Zsfc          !surface elevation (M)
REAL(KIND=real4) :: sunzen        !solar zenith angle(Degree)
REAL(KIND=real4) :: vzen        !satellite zenith angle(Degree)
REAL(KIND=real4) :: ihh        !cloudtop geometry height(M)
REAL(KIND=real4) :: height     !cloudtop geometry height above surface(KM)
INTEGER(KIND=int4) :: typee, ik       !cloud type
!
! local ion(OINTERs to fygat output POINTERs
INTEGER(KIND=int4), DIMENSION(:,:), POINTER:: ctype
! 2. begin program
  PRINT*,'--------------------------------------'
  PRINT*,'| Cloud Type Analysis Algorithm (II) |'
  PRINT*,'--------------------------------------'
  
!--- set local POINTERs to output structures
ctype => out2%cldtype2
!--- initialize to missing
ctype = missing_value_int4
!********
!---- analysis cloud type for each pixel
!
line_loop_1: DO iline= 1, sat%ny
element_loop_1: DO ielem= 1, sat%nx

      IF (sat%space_mask(ielem,iline) == sym%SPACE) THEN    
         CYCLE
      END IF
      
! channel 14 tbb,surface-elevation,cloud phase,cloud optical thickness,cloud effective radius,
! cloud top height,cloud top temperature
!
bt14 = sat%bt14(ielem,iline)
Zsfc = sat%zsfc(ielem,iline) 
sunzen = sat%solzen(ielem,iline)
vzen = sat%satzen(ielem,iline)
!******* waiting for change***************************************
cloudPhase  = sat%cldphase(ielem,iline)
cloudtopTem = sat%cldt(ielem,iline)
cloudtopHei = sat%cldz(ielem,iline)




!
!IF (bt14.eq.0.0) THEN
!ctype(ielem,iline)=-999.0
!GOTO 100
!ENDIF  

      
      !--- check for correct sensor and solar geometery  [65 degree is the upper limit for solar; 70 for sensor]  
      IF (vzen >= zen_max) THEN
         CYCLE
      END IF
      
      IF (sunzen >= solzen_max) THEN
         CYCLE 
      END IF
      
   cloudRad  = sat%cldreff(ielem,iline)
   cloudOpti = sat%cod_vis(ielem,iline)

      
!去掉不合理的卫星数据
IF (bt14.lt.160.0) THEN
   ctype(ielem,iline)=-999.0
   GOTO 100
ENDIF
IF (bt14.gt.380.0) THEN
   ctype(ielem,iline)=-999.0
   GOTO 100
ENDIF




!****************************** end waiting***********************
!将晴空像元赋值：0
if (cloudOpti == missing_value_real4 ) then
   ctype(ielem,iline)=0
   goto 100
endif
!将云顶位势高度转换为几何高度（米）
call AGRI_change(cloudtopHei,ihh)
!计算实际云顶高度（KM）
height = (ihh-Zsfc)/1000.0
if (height.le.0.0000) then
   ctype(ielem,iline)=0
   goto 100
endif
!输入云顶高度、云顶温度、窗区通道亮温、云相态、云有效粒子半径、云光学厚度，
!输出分析出的云类，0：晴空，2：AS/AC云，3：CU云，4：CI云，5：NS云，6：CB云，7：ST云，8：SC云，
!                  61：CI伴SC/ST的多层云，62：CI伴AS/AC的多层云，63：AS/AC伴ST/SC的多层云
!
call AGRI_cloudtype_analysis(height,cloudPhase,cloudRad,cloudOpti,Zsfc,cloudtopTem,bt14,typee)       
ctype(ielem,iline)=typee

100 CONTINUE

END DO element_loop_1
END DO line_loop_1
!!--- nullIFy POINTERs
ctype => null()
! 3. END SUBROUTINE   
END SUBROUTINE AGRI_cloudtype_II


!~~~~~~~~~~~~~~~~~~~ SUBROUTINE 2: AGRI_change ~~~~~~~~~~~~~~~~~~~~~~~~~~~~
subroutine AGRI_change(cloudtopHei,ihh)

REAL(KIND=real4)  :: cloudtopHei
REAL(KIND=real4)  :: g0,gi(11),gm,dh,r,gg,hhh,hi,ihh
data r/6370856/
!
dh=cloudtopHei/10
do i=1,11
hi=(i-1)*dh+r
gi(i)=9.8*(r/hi)**2
enddo
!
gg=0.0
do i=1,11
gg=gg+gi(i)
enddo
gm=gg/11
hhh=cloudtopHei*9.8/gm
ihh=hhh
end subroutine AGRI_change
!


!~~~~~~~~~~~~~~~~~~~ SUBROUTINE 3: AGRI_cloudtypeanalysis ~~~~~~~~~~~~~~~~~~~~~~~~~~~~
subroutine AGRI_cloudtype_analysis(height,phase,radius,opti,elevation,temp,tbb,typee)

real(KIND=real4)   :: height,radius,elevation,temp,tbb,minn,opti,dt
integer(KIND=int1) :: phase
real(KIND=real4)   :: dh(4),dr(4),dot(4),pdh(4),pdr(4),pdot(4),countt(4)
integer(KIND=int4) :: typee,ik
real(KIND=real4)   :: h(4),r(4),ot(4),hh(4)
real(KIND=real4)   :: ht(4)

!c**     coud micro properties for 4 cloud type(ST/SC,AC/AS,CU/CB,CIRRUS)（4种云的微物理特征）data h/1.3,3.5,3.3,9.5/
data r/13.5,17.0,27.5,55/
data ot/5.5,17.0,26.5,3.5/

!c      cloud top height over tibet（青藏高原4种云的云顶高度）
data ht/1.0,3.0,3.3,8.0/
!c
if(elevation.ge.3000.0) then 
do j=1,4
hh(j)=ht(j)
enddo
else
do j=1,4
hh(j)=h(j)
enddo
endif
!c
!c     多层云或深对流云或雨层云 
if(height.gt.6.5.and.opti.gt.8.0) goto 1001
if(opti.ge.50.0) goto 1002
!c      cloud type for fair weather （4种云类判别，最小距离法） 
do j=1,4
dh(j)=height-hh(j)
dr(j)=radius-r(j)
dot(j)=opti-ot(j)
enddo
do j=1,4
pdh(j)=0.5*abs(dh(j))/height
pdr(j)=0.25*abs(dr(j))/radius
pdot(j)=0.25*abs(dot(j))/opti
enddo
do j=1,4
countt(j)=pdh(j)+pdr(j)+pdot(j)
enddo
minn=999.0
do j=1,4
if(countt(j).le.minn) then
minn=countt(j)
ik=j
endif
enddo
!c       the results of cloud-type identification
if(ik.eq.1) then
!c       st/sc cloud
typee=1
goto 2000
endif
if(ik.eq.2) then
!c      as/ac cloud
typee=2
goto 2000
endif
if(ik.eq.3) then
!c      cu cloud
typee=3
goto 2000
endif
if(ik.eq.4) then
!c      cirrus
typee=4
goto 2000
endif
goto 2000
1002  continue
!c       雨层云   
!c      nimbus-stratus
if(height.gt.4.0.and.radius.lt.30.0) then
typee=5
goto 2000
endif
if(height.gt.4.0.and.radius.ge.30.0) then
typee=6
goto 2000
endif  
!c     AS/AC 云与SC/ST云重叠
typee=63
goto 2000
!c      多层云或深对流云或雨层云
1001  continue	         
if(opti.lt.19.0) then 
!c       cirrus over stratus/cumulus stratus
typee=61
goto 2000
endif
dt=tbb-temp
if(dt.gt.20.0) then
typee=61
goto 2000
endif
!c      cirrus over As/Ac
if(opti.ge.19.0.and.opti.lt.40.0) then
typee=62
goto 2000
endif  
!c**	 if(opti.ge.40.0.and.opti.lt.50.0.and.height.lt.10.0) then
if(opti.ge.40.0.and.height.lt.11.0) then 
!c       nimbus-stratus
typee=5
goto 2000
else
typee=6
endif
2000  continue
!c***      
!c***   进一步修正判别结果（从判别的SC/ST云中提取出CU和AS/AC云以及CI云）
!c***    
!c      
if(typee.eq.1.and.height.gt.3.5.and.height.lt.6.0) then
typee=2
goto 3000
endif
if(typee.eq.1.and.height.ge.6.0) then
typee=4
goto 3000
endif
!c***    从判别的AS/AC云中提取对流发展强的积雨云
if(typee.eq.2.and.height.gt.6.0.and.opti.gt.32.0) then
typee=6
goto 3000
endif
!c***  从判别的AS/AC云中提取ST/SC云 
if(typee.eq.2.and.height.lt.3.5.and.opti.lt.10.0) then
typee=1
goto 3000
endif 
!c***    从方法判别的AS/AC云中提取SC/ST云
if(typee.eq.2.and.height.lt.2.5) then
typee=1
goto 3000
endif
!c*** 从方法判别的卷云中提取AS/AC云  
if(typee.eq.4.and.height.lt.6.0) then
typee=2
goto 3000
endif 
3000  continue
!c*** 	从判别的AS/AC云中提取卷云CI
if(typee.eq.2.and.height.gt.6.0.and.opti.le.8.0) then
typee=4
goto 4000
endif  
if(typee.eq.2.and.opti.lt.2.0.and.height.gt.5.5) then
typee=4
goto 4000
endif   
!c***  
if(typee.eq.63.and.height.lt.3.0) then
typee=1
goto 4000
endif 	  
4000  continue
!c************************************************************
!c    进一步判识       
!c************************************************************
if(typee.eq.61) then
typee=62
goto 5000
endif
if(typee.eq.62.and.opti.gt.24) then
typee=5
goto 5000
endif
if(typee.eq.1.and.height.le.1.1) then
typee=7
goto 5000
endif
if(typee.eq.1.and.height.gt.1.1) then
typee=8
goto 5000
endif
if(typee.eq.6.and.height.lt.4.5) then
typee=3
goto 5000
endif
if(typee.eq.6.and.radius.lt.10.0) then
typee=5
goto 5000
endif
dt=tbb-temp
if(typee.eq.2.and.height.le.3.0.and.dt.lt.2.0) then
typee=8
goto 5000
endif
if(typee.eq.2.and.opti.gt.32.0) then
typee=63
goto 5000
endif
5000  continue
if(typee.eq.5.and.height.ge.11.0) then
typee=6
endif
dt=tbb-temp
if(typee.eq.6.and.dt.gt.15.0) then
typee=62
endif  
if(typee.eq.2.and.radius.gt.30.0) then
typee=3
endif  
if(typee.eq.8.and.radius.gt.25.0.and.phase.eq.1) then
typee=3
endif
if(typee.eq.7.and.radius.gt.25.0.and.phase.eq.1) then
typee=3
endif  
if(typee.eq.3.and.opti.gt.35.0) then
typee=6
endif 
if(typee.eq.5.and.dt.le.0.0) then
typee=6
endif 
if(typee.eq.5.and.dt.gt.20.0) then
typee=61
endif 	 
if(typee.eq.62.and.dt.gt.20.0) then
typee=61
endif
if(typee.eq.8.and.opti.gt.32.0) then
typee=3
endif
if(typee.eq.7.and.opti.gt.32.0) then
typee=3
endif
if(typee.eq.5.and.dt.le.0) then
typee=6
endif
if(typee.eq.8.and.dt.le.-2) then
typee=3
endif
if(typee.eq.7.and.dt.le.-2) then
typee=3
endif
!if(typee.eq.6.and.dt.gt.8) then
!typee=5
!endif
if(typee.eq.2.and.height.gt.6.0.and.opti.gt.24.0) then
typee=6
endif
if(typee.eq.61.and.opti.gt.24.0) then
typee=6
endif
if(typee.eq.62.and.opti.gt.24) then
typee=5
endif
if(typee.eq.6.and.radius.lt.25.0.and.height.lt.11.0) then
typee=5
endif
if(typee.eq.63.and.opti.gt.42.0) then
typee=5
endif
if(typee.eq.3.and.opti.gt.30.0) then
typee=5
endif
!if(typee.eq.8.and.opti.ge.16.0) then
!typee=5
!endif
!if(typee.eq.7.and.opti.ge.16.0) then
!typee=5
!endif
end subroutine AGRI_cloudtype_analysis


!++++++++++++++++++++ step 3: END module +++++++++++++++++++++++++++++++
END MODULE AGRI_cloud_type_II

